import sys
import time
import asyncio
from email_processor.email_client import get_access_token, fetch_unread_emails, forward_email, mark_email_as_read, force_mark_emails_as_read
#from apex_llm.apex import apex_categorise, apex_action_check
from config import EMAIL_ACCOUNTS, EMAIL_FETCH_INTERVAL, DEFAULT_EMAIL_ACCOUNT
#from apex_llm.apex_logging import create_log, add_to_log, update_acknowledged_status, insert_log_to_db, getDetailsByInteractionId
import datetime
import base64
#import apex_llm.apex as apex


processed_but_unread = set()

BATCH_SIZE =3  # Process 3 emails at a time - Cap for MS Graph

async def process_email(access_token, account, email_data, message_id):
    """
    Process a single email: categorize it, forward it, mark as read, and log it.
    Ensures single logging per email processed.
    """
    
    print(email_data)
    
    start_time = datetime.datetime.now()
    #log = create_log(email_data)
    #add_to_log("start_time", start_time, log)

    # try:
        
        # if await check_email_processed(email_data['internet_message_id']):
        #     print(f"Email {email_data['internet_message_id']} has already been processed. Skipping.")
        #     # Mark the email as read if it was already found in the database
        #     await mark_email_as_read(access_token, account, message_id)
        #     return
        
        # Concatenate email data for APEX processing
    llm_text = " ".join([str(value) for key, value in email_data.items() if key != 'email_object'])
    
    #await mark_email_as_read(access_token, account, message_id)
     
    try:
        
        # step 1 - get the xrsids from the email
        ## Get the email text 
        llm_text = " ".join([str(value) for key, value in email_data.items() if key != 'email_object'])
        
        # Get the xrsids from the email
        apex_interactionID = await apex.apex_get_iteractionID(str(llm_text))
               
        # Assuming the base64 encoded text is in apex_xrsids['message']['xrsid1']
        interactionID = str(apex_interactionID['message']['internalTicketReference'])


        # Use the interaction ID to query the customer email address from the original email - This will be used as the FORWARD_TO address in the forwarded email
        
        customer_email = await getDetailsByInteractionId(interactionID)
                
        if customer_email is not None:
            FORWARD_TO = customer_email
        else:
            FORWARD_TO = 'connexaibiztest@tihsa.co.za'
                
        reply_to_address = email_data['from']
        
        apex_post_cost_usd = apex_interactionID['message']['apex_cost_usd']
        
        # Update the APEX_POST_AGENT log 
        add_to_log("eml_to", FORWARD_TO, log)
        add_to_log("eml_frm", email_data['from'], log)
        add_to_log("interaction_id", interactionID, log)
        add_to_log("apex_cost_usd", apex_post_cost_usd, log)
    
        apex_post_processing_agent_compilation = True
        
        # If successful in compiling the apex_post_processing_agent details then move onto forwarding the email
        if apex_post_processing_agent_compilation == True:
            # Forward email
            forward_success = await forward_email(
                    access_token, 
                    account, 
                    message_id, 
                    reply_to_address, 
                    FORWARD_TO, 
                    email_data, 
                    "AI Forwarded message"
                ) 
            
            if forward_success:
                add_to_log("sts_eml_forward", "success", log)
                # Mark as read only if forwarding was successful
                marked_as_read = await mark_email_as_read(access_token, account, message_id)
                                
                if marked_as_read:
                    interaction_id = interactionID
                    # First update the acknowledged field and the acknowledged timestamp in the APEX log by searching the interaction_id and updating
                    update_apex_log = await update_acknowledged_status(interaction_id)
                    

            else:
                add_to_log("sts_eml_forward", "failed", log)
                # Pass having the email marked as read - This will keep it in the mailbin
        
        else:
            add_to_log("eml_to", "Error", log)
            add_to_log("eml_cc", "Error", log)
            add_to_log("eml_frm", "Error", log)
            add_to_log("interaction_id", "Error", log)
            add_to_log("apex_cost_usd", "Error", log)
            add_to_log("sts_eml_forward", "failed", log)

                     
        
    except Exception as e:
            add_to_log("eml_to", "Error", log)
            add_to_log("eml_cc", "Error", log)
            add_to_log("eml_frm", "Error", log)
            add_to_log("interaction_id", "Error", log)
            add_to_log("apex_cost_usd", "Error", log)
            add_to_log("sts_eml_forward", "failed", log)
            
            print(f"There was an error when processing the post mail - {e}")

         
    end_time = datetime.datetime.now()
    add_to_log("end_time", end_time, log)

    tat = (end_time - start_time).total_seconds()
    add_to_log("tat", tat, log)

    # Log the log to the post_logs db for APEX_POST_PROCESSING_AGENT
    try:
        await insert_log_to_db(log)
    except Exception as e:
        print("Failed to log record to DB due to error: ", e)
    
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
    
