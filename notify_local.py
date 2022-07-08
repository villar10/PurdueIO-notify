import os
import sys
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import requests
import time
import traceback
import smtplib
import ssl
from google.cloud import secretmanager


project_id = os.environ.get('GCP_PURDUEIO_PROJECT_ID')
email_id = os.environ.get('PURDUEIO_EMAIL_SECRET_ID')
password_id = os.environ.get('PURDUEIO_PASSWORD_SECRET_ID')
default_CRN_dict = {'Capacity': 0, 'Enrolled': 0, "Remaining": 0, "Full": True, "Subject": "AAA", "CourseNum": "99999", "CRN": "00000"}

CRN_inputs = []

# Use the application default credentials
cred = credentials.ApplicationDefault()
firebase_admin.initialize_app(cred, {
  'projectId': project_id,
})

db = firestore.client()

secret_client = secretmanager.SecretManagerServiceClient()
secret_email = f"projects/{project_id}/secrets/{email_id}/versions/latest"
secret_pass = f"projects/{project_id}/secrets/{password_id}/versions/latest"
print(secret_email)
# Access the secret version.
secret_email_response = secret_client.access_secret_version(request={"name": secret_email})
secret_pass_response = secret_client.access_secret_version(request={"name": secret_pass})

email_payload = secret_email_response.payload.data.decode("UTF-8")
pass_payload = secret_pass_response.payload.data.decode("UTF-8")



def newCRN(term, CRN_num):
    print(f"Adding CRN {CRN_num} to search.")
    path = term + '/CRN/' + CRN_num
    term_db = db.collection('term').document(path)
    CRN_data = default_CRN_dict
    term_db.set(CRN_data)

def deleteCRN(CRN_num):
    term = db.collection(u'term').document(u'2022fall').collections()
    for CRNs in term:
        selected = CRNs.document(CRN_num)
        selected.delete()

def wipeCRNs():
    term = db.collection(u'term').document(u'2022fall').collections()
    for CRNs in term:
        for CRN in CRNs.stream():
            #print(type(CRN))
            #CRN_data = CRN.to_dict()
            #print(f'{CRN.id} => {CRN_data}')
            #CRN_data["Capacity"] = 999
            #print(CRN_data)
            CRN.reference.delete()

def initialPopulate(term, CRN_num):
    pop = False
    path = term + '/CRN/' + CRN_num
    CRN_doc_ref = db.collection('term').document(path)
    CRN_doc = CRN_doc_ref.get()
    if CRN_doc.exists:
        CRN_data = CRN_doc.to_dict()
        #print(CRN_data)
    else:
        print(f"Error! CRN {CRN_num} in term {term} was not properly created in Firestore.")
        return
    term_code = "202310"    #TODO: This is setup as a constant but will need to change for future semesters
    getDataURL = f"http://api.purdue.io/odata/Sections?$filter=CRN eq '{CRN_num}' and Class/Term/Code eq '{term_code}'"
    req = requests.get(getDataURL)
    full_response = req.json()
    if len(full_response['value']) > 0:
        response_data = full_response['value'][0]
    else:
        print(f"CRN {CRN_num} does not exist in the term {term}. Please double check you have the correct CRN. Removing this CRN from search.")
        #CRN_inputs.remove(CRN_num)
        pop = True
        return pop
    #print(full_response['value'])
    #print(type(full_response['value']))
    capacity = response_data['Capacity']
    curr_enrolled = response_data['Enrolled']
    remaining = response_data['RemainingSpace']
    full = True if remaining <= 0 else False
    #TODO: Add logic to gather course Subject and Number at this point.

    CRN_data['Capacity'] = capacity
    CRN_data['Remaining'] = remaining
    CRN_data['Enrolled'] = curr_enrolled
    CRN_data['CRN'] = CRN_num
    CRN_data['Full'] = full
    
    #print(CRN_data)
    CRN_doc_ref.set(CRN_data)
    return pop

def updateCRN(term, CRN_num, email) -> bool:
    change_detected = False
    path = term + '/CRN/' + CRN_num
    CRN_doc_ref = db.collection('term').document(path)
    CRN_doc = CRN_doc_ref.get()
    if CRN_doc.exists:
        CRN_data = CRN_doc.to_dict()
        #print(CRN_data)
    else:
        print(f"Error! CRN {CRN_num} in term {term} was not properly created in Firestore.")
        return
    term_code = "202310"    #TODO: This is setup as a constant but will need to change for future semesters
    getDataURL = f"http://api.purdue.io/odata/Sections?$filter=CRN eq '{CRN_num}' and Class/Term/Code eq '{term_code}'"
    req = requests.get(getDataURL)
    if req.status_code == 200:
        full_response = req.json()
        response_data = full_response['value'][0]
    else:
        print(f"Non 200 return received. Return code: {req.status_code}")
        return

    capacity = response_data['Capacity']
    curr_enrolled = response_data['Enrolled']
    prev_full_flag = CRN_data['Full']
    remaining = response_data['RemainingSpace']
    if not ((capacity == CRN_data['Capacity']) and (curr_enrolled == CRN_data['Enrolled']) and (remaining == CRN_data['Remaining'])):
        new_full_flag = True if remaining <= 0 else False
        if prev_full_flag != new_full_flag: #A change in status has occured, send an email.
            change_detected = True
            #send email here
            prev_stat_string = "Closed" if prev_full_flag else "Open"
            new_stat_string = "Closed" if new_full_flag else "Open"
            print(f"Sending email to {email}. Status of CRN {CRN_num} has changed from {prev_stat_string} to {new_stat_string}.")
            #Setup Email
            smtp_server_domain_name = 'smtp.gmail.com'
            smtp_port = 465
            ssl_context = ssl.create_default_context()
            email_server = smtplib.SMTP_SSL(smtp_server_domain_name, smtp_port, context=ssl_context)
            email_server.login(email_payload, pass_payload)          #TODO: Change this to gather from Google Secrets Manager
            #result = email_server.sendmail('purdueionotify@gmail.com', 'ryanvillarreal116@gmail.com', f"Subject: {subject}\n{content}")
            result = email_server.sendmail(email_payload, email, f"Subject: PurdueIO Notify: Change Detected for CRN {CRN_num}\nStatus of CRN {CRN_num} has changed from {prev_stat_string} to {new_stat_string}.\nCurrent Enrollment: {curr_enrolled}\nCapacity: {capacity}\nSeats Remaining: {remaining}\n\nThis message was sent automatically. For support, reply to this message or email purdueIOnotify@gmail.com")
            email_server.quit()



        CRN_data['Capacity'] = capacity
        CRN_data['Remaining'] = remaining
        CRN_data['Enrolled'] = curr_enrolled
        CRN_data['Full'] = new_full_flag

        #print(CRN_data)
        CRN_doc_ref.set(CRN_data)
    return change_detected
    

def updateAllData(term, email):
    print(f"\nChecking for changes in CRNs {CRN_inputs}.")
    change_detected = False
    for CRN in CRN_inputs:
        curr_change_detected = updateCRN(term, CRN, email)
        if curr_change_detected:
            change_detected = True
    if not change_detected:
        print("No changes detected.")
    




def taskLoop(occurence, task, term, email): #Adapted from https://stackoverflow.com/a/49801719
    next_time = time.time() + occurence
    while True:
        time.sleep(max(0, next_time - time.time()))
        try:
            task(term, email)
        except Exception:
            traceback.print_exc()
        # in production code you might want to have this instead of course:
        # logger.exception("Problem while executing repetitive task.")
        # skip tasks if we are behind schedule:
        next_time += (time.time() - next_time) // occurence * occurence + occurence




def main():
    wipeCRNs()      #This will completely mess things up if multiple users are running the program at once
    CRN_input = ""
    #CRN_inputs = []
    try:
        #term_selected = input("Enter term you would like to track (eg. 2022fall): ")
        term_selected = '2022fall'
        email_confirmed = False
        while not email_confirmed:
            email = input("Enter email you would like to receive updates at: ")
            email_selection = input(f"Is this the correct email? [Y/n]\n{email}\n")
            if email_selection == "Y" or email_selection == "y" or email_selection == "yes" or email_selection == "Yes":
                email_confirmed = True
        while(True):
            if len(CRN_inputs):
                print("\nCRNs to track: ", CRN_inputs)
            CRN_input = input("Enter CRN to track one at a time, type \"Submit\" when all CRNs are entered, or \"Clear\" to restart: ")
            #print(CRN_input)
            if(CRN_input == "Submit" or CRN_input == "submit"):
                break
            if CRN_input == "Clear" or CRN_input == "clear":
                CRN_inputs.clear()
            elif((len(CRN_input) == 5) and (CRN_input not in CRN_inputs) and (CRN_input.isdigit())):
                try:
                    int(CRN_input)
                    CRN_inputs.append(CRN_input)
                except:
                    print("Invalid number given.")

            else:
                print("Invalid or duplicate CRN given.")
    except:
        exit(0)
    #print(CRN_input)
    bad_crns = []
    for CRN in CRN_inputs:
        pop = False
        newCRN(term_selected, CRN)
        pop = initialPopulate(term_selected, CRN)
        if pop:
            bad_crns.append(CRN)
    for CRN in bad_crns:
        CRN_inputs.remove(CRN)
        deleteCRN(CRN)


    print("Beginning search routine. CRNs will be checked every minute for significant changes.")
    #Now begin one minute loop and update all CRNs that are being tracked.
    taskLoop(60, updateAllData, term_selected, email)

        

if __name__ == '__main__':
    sys.exit(main())