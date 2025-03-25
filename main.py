import sys
import time
import asyncio
from email_processor.email_client import get_access_token, fetch_unread_emails, forward_email, mark_email_as_read, force_mark_emails_as_read
from email_processor.email_utils import generate_llm_text
from config import EMAIL_ACCOUNTS, EMAIL_FETCH_INTERVAL, DEFAULT_EMAIL_ACCOUNT
import datetime
import json
import os
from functions import * 
import extraction_templates
import functions as func


processed_but_unread = set()

client = get_openai_client()


BATCH_SIZE = 3  # Process 3 emails at a time - Cap for MS Graph

async def process_email(access_token, account, email_data, message_id):
    """
    Process a single email: extract all information including attachment text using Document Intelligence,
    categorize it, forward it, mark as read, and log it.
    """
    
    print(f"Processing email with subject: {email_data['subject']}")
    
    start_time = datetime.datetime.now()

    try:
        # Generate the complete LLM text (JSON) including email details and attachment content
        llm_text = generate_llm_text(email_data)
               
        # Parse the JSON to get summary information for logging
        llm_data = json.loads(llm_text)
        
        # STEP 1: Pass the email_data to a GPT-4o model to classify the tracker company
        ava_compiliation = {}
        ava_result = {}
        
        try:
            tracker_company_response = get_tracking_company(llm_data)
                        
            result = tracker_company_response.choices[0].message.content
            result = json.loads(result)
            ava_compiliation.update(result)
            
            tracker_company_input_tokens = tracker_company_response.usage.prompt_tokens
            tracker_company_completion_tokens = tracker_company_response.usage.completion_tokens
            tracker_company_output_tokens = tracker_company_response.usage.total_tokens
            tracker_company_cached_tokens = tracker_company_response.usage.cached_tokens if hasattr(tracker_company_response.usage, 'cached_tokens') else None

        except Exception as e:
            print(f"Error obtain the tracker company using gpt4o: {str(e)}")
            ava_compiliation.update({"tracker_company": "error"})

        ## STEP 2: EXTRACT A POLICY NUMBER FROM THE EMAIL CONTEXT
                    
        try:
            polno_response = get_policy_number(llm_data)
            
            result = polno_response.choices[0].message.content
            result = json.loads(result)
            ava_compiliation.update(result)
            
            polno_input_tokens = polno_response.usage.prompt_tokens
            polno_completion_tokens = polno_response.usage.completion_tokens
            polno_output_tokens = polno_response.usage.total_tokens
            polno_cached_tokens = polno_response.usage.cached_tokens if hasattr(polno_response.usage, 'cached_tokens') else None
        
        except Exception as e:
            print(f"Error obtaining the policy number from the mail context: {str(e)}")
            ava_compiliation.update({"policy_number": "error"})

        
        # STEP 3 - GET THE ID NUMBER
        try:
            idNumber_response = get_id_number(llm_data)
            result = idNumber_response.choices[0].message.content
            result = json.loads(result)
            ava_compiliation.update(result)
            
            idNumber_input_tokens = idNumber_response.usage.prompt_tokens
            idNumber_completion_tokens = idNumber_response.usage.completion_tokens
            idNumber_output_tokens = idNumber_response.usage.total_tokens
            idNumber_cached_tokens = idNumber_response.usage.cached_tokens if hasattr(idNumber_response.usage, 'cached_tokens') else None
            
        except Exception as e:
            print(f"Error obtaining the ID number from the mail context: {str(e)}")
            ava_compiliation.update({"id_number": "error"})
         
        
        # STEP 4 - EXTRACT THE CERTIFICATE DETAILS
        try:
            if ava_compiliation['tracker_company'] in extraction_templates.available_tempates:
                
                cert_response = extract_details(llm_data, extraction_templates.templates[ava_compiliation['tracker_company']])
                result = cert_response.choices[0].message.content
                result = json.loads(result)
                
                
                cert_input_tokens = cert_response.usage.prompt_tokens
                cert_completion_tokens = cert_response.usage.completion_tokens
                cert_output_tokens = cert_response.usage.total_tokens
                cert_cached_tokens = cert_response.usage.cached_tokens if hasattr(cert_response.usage, 'cached_tokens') else None
                
                for key in result:
                    ava_compiliation.update({key: result[key]})
                
                
                # Compile the vehicle key string for similarity check
                
                # YEAR, MAKE AND MODEL AVAILABLE
                if ava_compiliation["vehicle_year"] != "not_found" and ava_compiliation["vehicle_make"] != "not_found" and ava_compiliation["vehicle_model"] != "not_found":
                    ava_compiliation.update({"vehicle_key": (ava_compiliation["vehicle_year"].lower() + ava_compiliation["vehicle_make"].lower() + ava_compiliation["vehicle_model"].lower()).replace(" ", "")})
                
                # MAKE AND MODEL AVAILABLE ONLY
                elif ava_compiliation["vehicle_make"] != "not_found" and ava_compiliation["vehicle_model"] != "not_found":
                    ava_compiliation.update({"vehicle_key": (ava_compiliation["vehicle_make"].lower() + ava_compiliation["vehicle_model"].lower()).replace(" ", "")})
                           
                else:
                    ava_compiliation.update({"vehicle_key": "not_found"})
                
            else: 
                print(f"Template not available for {ava_compiliation['tracker_company']}")
                ava_compiliation.update({"vin_number": "not_found"})
                ava_compiliation.update({"engine_number": "not_found"})
                ava_compiliation.update({"registration_number": "not_found"})
                ava_compiliation.update({"vehicle_year": "not_found"})
                ava_compiliation.update({"vehicle_make": "not_found"})
                ava_compiliation.update({"vehicle_model": "not_found"})
                ava_compiliation.update({"contract_number": "not_found"})
                ava_compiliation.update({"fitment_date": "not_found"})
                ava_compiliation.update({"product_name": "not_found"})
                ava_compiliation.update({"vehicle_key": "not_found"})
                
        except Exception as e:
            print(f"Error obtaining the certificate details from the mail context: {str(e)}")
            ava_compiliation.update({"vin_number": "error"})
            ava_compiliation.update({"engine_number": "error"})
            ava_compiliation.update({"registration_number": "error"})
            ava_compiliation.update({"vehicle_year": "error"})
            ava_compiliation.update({"vehicle_make": "error"})
            ava_compiliation.update({"vehicle_model": "error"})
            ava_compiliation.update({"contract_number": "error"})
            ava_compiliation.update({"fitment_date": "error"})
            ava_compiliation.update({"product_name": "error"})
            ava_compiliation.update({"vehicle_key": "not_found"})

        print(ava_compiliation)
        
        try:
            ## GET A TOKEN FROM THE TOKEN SERVICE
            token =func.get_token()

        except Exception as e:
            print(f"Error obtaining the token from the token service: {str(e)}")
        
        
        try: 
            # STEP 5 - CALL AS400 TO GET VEHICLE DETAILS
            ## ATTEMPT 1 : TRY WITH POLICY NUMBER
            
            if ava_compiliation["policy_number"] not in ['not_found', '']: 
                
                print(f"Attempting to use policy number to get vehicle details")
                
                ava_result.update({"ava_lookup_method":"policy_number"})
                
                # USE THE POLICY NUMBER TO GET THE VEHICLES DETAILS ON THE POLICY 
                vehicles_list = func.get_vehicles(token, ava_compiliation["policy_number"])
                                
                # UNPACK THE VEHICLE LIST
                for vehicle_sequence in vehicles_list:
                    
                    # CREATE THE VEHICLE KEY STRING FOR SIMILARITY CHECK
                    # CHECK IF THE VEHICLE MAKE IS INCLUDED IN THE MODEL LISTING - SOMETIME THE MODEL STRING HAS THE MAKE STRING INCLUDED WHICH CREATES A DUPLICATE THAT THROWS OFF THE SIMILARITY MATCH
                    if vehicles_list[vehicle_sequence]["make"].lower() in vehicles_list[vehicle_sequence]["model"].lower():
                        # IF MODEL STRING INCLUDES MAKE STRING THEN STRIP OUT THE MAKE STRING FROM THE MODEL STRING
                        as400_vehicle_string = vehicles_list[vehicle_sequence]["year"].lower() + vehicles_list[vehicle_sequence]["make"].lower() + vehicles_list[vehicle_sequence]["model"].lower().replace(vehicles_list[vehicle_sequence]["make"].lower(), "")
                    else:
                        # OTHERWISE CONCATENATE THE YEAR, MAKE AND MODEL STRINGS
                        as400_vehicle_string = vehicles_list[vehicle_sequence]["year"].lower() + vehicles_list[vehicle_sequence]["make"].lower() + vehicles_list[vehicle_sequence]["model"].lower()
                        
                    as400_vehicle_string = as400_vehicle_string.replace(" ", "")
                    
                    text_similarity_score = func.text_similarity_score(ava_compiliation["vehicle_key"], as400_vehicle_string, SentenceTransformer('all-MiniLM-L6-v2'))
                    print(f"Extracted vehicle key",ava_compiliation["vehicle_key"])
                    print(f"AS400 vehicle key",as400_vehicle_string)
                    print(f"Text similarity score", text_similarity_score)
                                        
                    # MATCH ATTEMPT 1 - USE VIN
                    if ava_compiliation["vin_number"].replace(" ", "").lower() == vehicles_list[vehicle_sequence]["vinNumber"].replace(" ", "").lower():
                        for key in vehicles_list[vehicle_sequence]:
                            ava_result.update({key:vehicles_list[vehicle_sequence][key]})
                            ava_result.update({"ava_validation_method":"VIN NUMBER"})
                    
                    # MATCH ATTEMPT 2 - USE ENGINE NUMBER        
                    elif ava_compiliation["engine_number"].replace(" ", "").lower() == vehicles_list[vehicle_sequence]["engineNumber"].replace(" ", "").lower():
                        for key in vehicles_list[vehicle_sequence]:
                            ava_result.update({key:vehicles_list[vehicle_sequence][key]})   
                            ava_result.update({"ava_validation_method":"ENGINE NUMBER"})
                            
                    # MATCH ATTEMPT 3 - USE REGISTRATION NUMBER
                    elif ava_compiliation["registration_number"].strip().lower() == vehicles_list[vehicle_sequence]["registrationNumber"].strip().lower():
                        for key in vehicles_list[vehicle_sequence]:
                            ava_result.update({key:vehicles_list[vehicle_sequence][key]})
                            ava_result.update({"ava_validation_method":"REGISTRATION NUMBER"})
                    
                    # MATCH ATTEMPT 4 - USE VEHICLE YEAR, MAKE AND MODEL
                    elif text_similarity_score > 0.8:
                        for key in vehicles_list[vehicle_sequence]:
                            ava_result.update({key:vehicles_list[vehicle_sequence][key]})
                            ava_result.update({"ava_validation_method":"TEXT SIMILARITY"})
                    
                    # NO MATCHES FOUND
                    else:
                        ava_result.update({'year': 'validation_unsuccessfull'})
                        ava_result.update({'make': 'validation_unsuccessfull'})
                        ava_result.update({'model': 'validation_unsuccessfull'})
                        ava_result.update({'colour': 'validation_unsuccessfull'})
                        ava_result.update({'registrationNumber': 'validation_unsuccessfull'})
                        ava_result.update({'vinNumber': 'validation_unsuccessfull'})
                        ava_result.update({'engineNumber': 'validation_unsuccessfull'})
                        ava_result.update({'riskItemSequenceNumber': 'validation_unsuccessfull'})
                        ava_result.update({'coverTypeDescription': 'validation_unsuccessfull'})
                        ava_result.update({'statusDescription': 'validation_unsuccessfull'})
                        ava_result.update({'vehicleActiveIndicator': 'validation_unsuccessfull'})
                        ava_result.update({"ava_validation_method":"validation_unsuccessfull"})
            
            elif ava_compiliation["id_number"] not in ['not_found', '']: 
                ava_result.update({"ava_lookup_method":"id_number"})
                
                
                # USE THE ID NUMBER TO GET THE LIST OF ACTIVE POLICIES
                response = func.get_active_policies(ava_compiliation["id_number"],token)

                # SUCCESSFUL RESPONSE
                if response["response_code"] == 200:
                    activePolices = response["activePolicies"]
                    
                    # RUN A LOOP TO GO THROUGH ALL THE ACTIVE POLICIES TO FIND A MATCH ON THE TRACKER DOCUMENT
                    for policyNumber in activePolices:
                        vehicles_list = func.get_vehicles(token, policyNumber)
                        
                        # UNPACK THE VEHICLE LIST
                        for vehicle_sequence in vehicles_list:
                            
                            # CREATE THE VEHICLE KEY STRING FOR SIMILARITY CHECK
                            # CHECK IF THE VEHICLE MAKE IS INCLUDED IN THE MODEL LISTING - SOMETIME THE MODEL STRING HAS THE MAKE STRING INCLUDED WHICH CREATES A DUPLICATE THAT THROWS OFF THE SIMILARITY MATCH
                            if vehicles_list[vehicle_sequence]["make"].lower() in vehicles_list[vehicle_sequence]["model"].lower():
                                # IF MODEL STRING INCLUDES MAKE STRING THEN STRIP OUT THE MAKE STRING FROM THE MODEL STRING
                                as400_vehicle_string = vehicles_list[vehicle_sequence]["year"].lower() + vehicles_list[vehicle_sequence]["make"].lower() + vehicles_list[vehicle_sequence]["model"].lower().replace(vehicles_list[vehicle_sequence]["make"].lower(), "")
                            else:
                                # OTHERWISE CONCATENATE THE YEAR, MAKE AND MODEL STRINGS
                                as400_vehicle_string = vehicles_list[vehicle_sequence]["year"].lower() + vehicles_list[vehicle_sequence]["make"].lower() + vehicles_list[vehicle_sequence]["model"].lower()
                                
                            as400_vehicle_string = as400_vehicle_string.replace(" ", "")
                            
                            text_similarity_score = func.text_similarity_score(ava_compiliation["vehicle_key"], as400_vehicle_string, SentenceTransformer('all-MiniLM-L6-v2'))
                            print(f"Extracted vehicle key",ava_compiliation["vehicle_key"])
                            print(f"AS400 vehicle key",as400_vehicle_string)
                            print(f"Text similarity score", text_similarity_score)
                                                
                            # MATCH ATTEMPT 1 - USE VIN
                            if ava_compiliation["vin_number"].replace(" ", "").lower() == vehicles_list[vehicle_sequence]["vinNumber"].replace(" ", "").lower():
                                for key in vehicles_list[vehicle_sequence]:
                                    ava_result.update({key:vehicles_list[vehicle_sequence][key]})
                                    ava_result.update({"ava_validation_method":"VIN NUMBER"})
                            
                            # MATCH ATTEMPT 2 - USE ENGINE NUMBER        
                            elif ava_compiliation["engine_number"].replace(" ", "").lower() == vehicles_list[vehicle_sequence]["engineNumber"].replace(" ", "").lower():
                                for key in vehicles_list[vehicle_sequence]:
                                    ava_result.update({key:vehicles_list[vehicle_sequence][key]})   
                                    ava_result.update({"ava_validation_method":"ENGINE NUMBER"})
                                    
                            # MATCH ATTEMPT 3 - USE REGISTRATION NUMBER
                            elif ava_compiliation["registration_number"].strip().lower() == vehicles_list[vehicle_sequence]["registrationNumber"].strip().lower():
                                for key in vehicles_list[vehicle_sequence]:
                                    ava_result.update({key:vehicles_list[vehicle_sequence][key]})
                                    ava_result.update({"ava_validation_method":"REGISTRATION NUMBER"})
                            
                            # MATCH ATTEMPT 4 - USE VEHICLE YEAR, MAKE AND MODEL
                            elif text_similarity_score > 0.8:
                                for key in vehicles_list[vehicle_sequence]:
                                    ava_result.update({key:vehicles_list[vehicle_sequence][key]})
                                    ava_result.update({"ava_validation_method":"TEXT SIMILARITY"})
                                
                            # NO MATCHES FOUND
                            else:
                                ava_result.update({'year': 'validation_unsuccessfull'})
                                ava_result.update({'make': 'validation_unsuccessfull'})
                                ava_result.update({'model': 'validation_unsuccessfull'})
                                ava_result.update({'colour': 'validation_unsuccessfull'})
                                ava_result.update({'registrationNumber': 'validation_unsuccessfull'})
                                ava_result.update({'vinNumber': 'validation_unsuccessfull'})
                                ava_result.update({'engineNumber': 'validation_unsuccessfull'})
                                ava_result.update({'riskItemSequenceNumber': 'validation_unsuccessfull'})
                                ava_result.update({'coverTypeDescription': 'validation_unsuccessfull'})
                                ava_result.update({'statusDescription': 'validation_unsuccessfull'})
                                ava_result.update({'vehicleActiveIndicator': 'validation_unsuccessfull'})
                                ava_result.update({"ava_validation_method":"validation_unsuccessfull"})

                        
                else:
                    # Handle errors for failed requests for activePolicy numbers
                    print(f"There was an error getting the active policies with the provided ID Number")
                                
                
                                             
            print("AVA RESULTS")
            print(ava_result)
                
        except Exception as e:
            print(f"Error obtaining the vehicle details from the AS400: {str(e)}")
         
                
        # if customer_email is not None:
        #     FORWARD_TO = customer_email
        # else:
        #     FORWARD_TO = 'connexaibiztest@tihsa.co.za'
                
        # reply_to_address = email_data['from']
        
        # apex_post_cost_usd = apex_interactionID['message']['apex_cost_usd']
        
        # # Update the APEX_POST_AGENT log 
        # add_to_log("eml_to", FORWARD_TO, log)
        # add_to_log("eml_frm", email_data['from'], log)
        # add_to_log("interaction_id", interactionID, log)
        # add_to_log("apex_cost_usd", apex_post_cost_usd, log)
    
        # # Forward email
        # forward_success = await forward_email(
        #         access_token, 
        #         account, 
        #         message_id, 
        #         reply_to_address, 
        #         FORWARD_TO, 
        #         email_data, 
        #         "AI Forwarded message"
        #     ) 
        
        # if forward_success:
        #     add_to_log("sts_eml_forward", "success", log)
        #     # Mark as read only if forwarding was successful
        #     marked_as_read = await mark_email_as_read(access_token, account, message_id)
                            
        #     if marked_as_read:
        #         interaction_id = interactionID
        #         # First update the acknowledged field and the acknowledged timestamp in the APEX log
        #         update_apex_log = await update_acknowledged_status(interaction_id)
        # else:
        #     add_to_log("sts_eml_forward", "failed", log)
        # """
        
        # For testing purposes
        # Uncomment the following line when testing
        # await mark_email_as_read(access_token, account, message_id)
        
    except Exception as e:
        # add_to_log error handling code here
        print(f"Error processing email: {str(e)}")
         
    end_time = datetime.datetime.now()
    # add_to_log("end_time", end_time, log)

    tat = (end_time - start_time).total_seconds()
    # add_to_log("tat", tat, log)
    print(f"Email processing completed in {tat:.2f} seconds")

    # Uncomment when ready to log to database
    # try:
    #     await insert_log_to_db(log)
    # except Exception as e:
    #     print("Failed to log record to DB due to error: ", e)
    
async def process_batch():
    
    access_token = await get_access_token()
    
    for account in EMAIL_ACCOUNTS:
        print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Fetching unread emails for: {account}")
        try:
            all_unread_emails = await fetch_unread_emails(access_token, account)
            
        except Exception as e:
            print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: process_batch - Error fetching unread emails for {account}: {str(e)}")
            continue  # Skip to the next account if there's an error fetching emails

        print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: process_batch - Processing {len(all_unread_emails)} unread emails in batch")
        for i in range(0, len(all_unread_emails), BATCH_SIZE):
            batch = all_unread_emails[i:i+BATCH_SIZE]
            tasks = [asyncio.create_task(process_email(access_token, account, email_data, message_id)) 
                     for email_data, message_id in batch]
            await asyncio.gather(*tasks, return_exceptions=True)
            
            # Add a small delay between batches to avoid overwhelming the API
            await asyncio.sleep(1)


async def main():
    while True:
        start_time = time.time()
        
        try:
            await process_batch()
        except Exception as e: 
            print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: main - There was an error processing the batch due to:  {e}")

        elapsed_time = time.time() - start_time
        if elapsed_time < EMAIL_FETCH_INTERVAL:
            await asyncio.sleep(EMAIL_FETCH_INTERVAL - elapsed_time)

def trigger_email_triage():
    if len(sys.argv) > 1 and sys.argv[1] == 'start':
        asyncio.run(main())
    else:
        print("To start the email processing, run with 'start' argument")
        print("Run Command: python main.py start")

if __name__ == '__main__':
    trigger_email_triage()
