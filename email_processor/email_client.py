import aiohttp
import asyncio
import datetime
import time
from msal import ConfidentialClientApplication
from config import MS_CLIENT_ID, TENANT_ID, MS_CLIENT_SECRET, AUTHORITY, SCOPE
from email_processor.email_utils import create_email_details

async def get_access_token():
    app = ConfidentialClientApplication(
        MS_CLIENT_ID,
        authority=AUTHORITY,
        client_credential=MS_CLIENT_SECRET,
    )
    result = await asyncio.to_thread(app.acquire_token_for_client, scopes=SCOPE)
    if 'access_token' in result:
        return result['access_token']
    else:
        print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client - Function: get_access_token - Failed to obtain access token.")
        print(result.get('error'))
        print(result.get('error_description'))
        return None

async def fetch_unread_emails(access_token, user_id):
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
    }

    endpoint = f'https://graph.microsoft.com/v1.0/users/{user_id}/messages?$filter=isRead eq false'
    
    async with aiohttp.ClientSession() as session:
        async with session.get(endpoint, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                messages = data.get('value', [])
                email_details_list = [
                    (await create_email_details(access_token, user_id, msg), msg['id']) for msg in messages
                ]
                return email_details_list
            else:
                print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client.py - Function: fetch_unread_emails - Failed to retrieve messages for user {user_id}: {response.status}")
                print(await response.text())
                return []
            
async def mark_email_as_read(access_token: str, user_id: str, message_id: str, max_retries: int = 3) -> bool:
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
    }
    endpoint = f'https://graph.microsoft.com/v1.0/users/{user_id}/messages/{message_id}'
    body = {
        'isRead': True
    }
    
    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.patch(endpoint, headers=headers, json=body) as response:
                    if response.status == 200:
                        print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client.py - Function: mark_email_as_read - Marked message {message_id} as read.")
                        return True
                    else:
                        print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client.py - Function: mark_email_as_read - Failed to mark message {message_id} as read: {response.status}")
                        print(await response.text())
        except Exception as e:
            print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client.py - Function: mark_email_as_read - Error marking message {message_id} as read: {str(e)}")
        
        if attempt < max_retries - 1:
            await asyncio.sleep(2 ** attempt)  # Exponential backoff
    
    return False

async def force_mark_emails_as_read(access_token: str, user_id: str, message_ids: list) -> dict:
    results = {}
    for message_id in message_ids:
        success = await mark_email_as_read(access_token, user_id, message_id)
        results[message_id] = success
    return results

async def forward_email(access_token, user_id, message_id, original_sender, forward_to, email_data, forwardMsg=""):
    
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': "application/json; odata.metadata=minimal; odata.streaming=true; IEEE754Compatible=false; charset=utf-8",
    }
    
    async with aiohttp.ClientSession() as session:
        
        try:
            
            # GATHER EMAIL DETAILS TO CHECK IF EMAIL HAS ATTACHMENTS
            email_details_endpoint = f'https://graph.microsoft.com/v1.0/users/{user_id}/messages/{message_id}/'
            
            async with session.get(email_details_endpoint , headers=headers) as get_response:
                if get_response.status != 200:
                    print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client.py - Function: forward_email - Failed to get original message: {get_response.status}")
                    print(await get_response.text())
                
                original_message = await get_response.json()
                
                # Format CC recipients from comma-separated string
                cc_recipients = []
                if email_data.get('cc'):
                    # Split the CC string and remove any whitespace
                    cc_list = [email.strip() for email in email_data['cc'].split(',') if email.strip()]
                    # Create properly formatted recipient objects for each CC
                    cc_recipients = [
                        {
                            "emailAddress": {
                                "address": cc
                            }
                        } for cc in cc_list if cc  # Additional check to ensure no empty emails
                    ]
                 
                # CHECK IF EMAIL HAS ATTACHMENTS               
                if original_message.get('hasAttachments') == True: # CHECK THF ATTACHMENT STATUS IF EMAIL HAS ATTACHMENTS
                    
                    get_attachments_endpoint = f'https://graph.microsoft.com/v1.0/users/{user_id}/messages/{message_id}/attachments'
                    async with session.get(get_attachments_endpoint, headers=headers) as get_attachments_response:
                        
                        get_attachments_data = await get_attachments_response.json() 
                        
                        if get_attachments_data.get('value')[0]['name'] == "Safe Attachments Scan In Progress":
                            return False 
                        
                        else:  # FORWARD EMAIL IF NOT ATTACHMENTS

                            # CREATE THE FORWARD EMAIL DRAFT
                            create_forward_endpoint = f'https://graph.microsoft.com/v1.0/users/{user_id}/messages/{message_id}/createForward'
                            async with session.post(create_forward_endpoint, headers=headers) as create_response:
                                if create_response.status != 201:
                                    print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client.py - Function: forward_email - Failed to create forward: {create_response.status}")
                                    print(await create_response.text())
                                    return False
                                
                                forward_message = await create_response.json()
                                forward_id = forward_message['id']

                            # UPDATE THE FORWARD EMAIL WITH CUSTOMER HEADER
                            update_endpoint = f'https://graph.microsoft.com/v1.0/users/{user_id}/messages/{forward_id}'
                            update_body = {
                                # "sender": [
                                #     {
                                #         "emailAddress": {
                                #             "address": original_sender
                                #         }
                                #     }
                                # ],
                                "toRecipients": [
                                    {
                                        "emailAddress": {
                                            "address": forward_to
                                        }
                                    }
                                ],
                                "ccRecipients": cc_recipients if cc_recipients else [],
                                "replyTo": [
                                    {
                                        "emailAddress": {
                                            "address": original_sender
                                        }
                                    }
                                ],
                                "body": {
                                    "contentType": forward_message['body']['contentType'],
                                    "content": f"{forward_message['body']['content']}"
                                }
                            }

                            async with session.patch(update_endpoint, headers=headers, json=update_body) as update_response:
                                if update_response.status != 200:
                                    print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client.py - Function: forward_email - Failed to update forward: {update_response.status}")
                                    print(await update_response.text())
                                    return False

                            # FORWARD THE EMAIL
                            send_endpoint = f'https://graph.microsoft.com/v1.0/users/{user_id}/messages/{forward_id}/send'
                            async with session.post(send_endpoint, headers=headers) as send_response:
                                if send_response.status != 202:
                                    print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client.py - Function: forward_email - Failed to send forward: {send_response.status}")
                                    print(await send_response.text())
                                    return False
                                
                                print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client.py - Function: forward_email - Successfully forwarded message to {forward_to} with reply-to set to {original_sender}")
                                return True

                else: # FORWARD THE EMAIL IF NO ATTACHMENTS PRESENT          
                    
                    # CREATE THE FORWARD EMAIL DRAFT
                    create_forward_endpoint = f'https://graph.microsoft.com/v1.0/users/{user_id}/messages/{message_id}/createForward'
                    async with session.post(create_forward_endpoint, headers=headers) as create_response:
                        if create_response.status != 201:
                            print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client.py - Function: forward_email - Failed to create forward: {create_response.status}")
                            print(await create_response.text())
                            return False
                        forward_message = await create_response.json()
                        forward_id = forward_message['id']

                    # UPDATE THE FORWARD EMAIL WITH CUSTOMER HEADER
                    update_endpoint = f'https://graph.microsoft.com/v1.0/users/{user_id}/messages/{forward_id}'
                    update_body = {
                        # "sender": [
                        #     {
                        #         "emailAddress": {
                        #             "address": original_sender
                        #         }
                        #     }
                        # ],
                        "toRecipients": [
                            {
                                "emailAddress": {
                                    "address": forward_to
                                }
                            }
                        ],
                        "ccRecipients": cc_recipients if cc_recipients else [],
                        "replyTo": [
                            {
                                "emailAddress": {
                                    "address": original_sender
                                }
                            }
                        ],
                        "body": {
                            "contentType": forward_message['body']['contentType'],
                            "content": f"{forward_message['body']['content']}"
                        }
                    }

                    async with session.patch(update_endpoint, headers=headers, json=update_body) as update_response:
                        if update_response.status != 200:
                            print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client.py - Function: forward_email - Failed to update forward: {update_response.status}")
                            print(await update_response.text())
                            return False

                   # FORWARD THE EMAIL
                    send_endpoint = f'https://graph.microsoft.com/v1.0/users/{user_id}/messages/{forward_id}/send'
                    async with session.post(send_endpoint, headers=headers) as send_response:
                        if send_response.status != 202:
                            print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client.py - Function: forward_email - Failed to send forward: {send_response.status}")
                            print(await send_response.text())
                            return False
                        
                        print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client.py - Function: forward_email - Successfully forwarded message to {forward_to} with reply-to set to {original_sender}")
                        return True
                        
        except Exception as e:
            print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client.py - Function: forward_email - An error occurred: {str(e)}")
            return False
                
# Keeping the synchronous version for compatibility with existing code
def get_access_token_sync():
    return asyncio.run(get_access_token())

def fetch_unread_emails_sync(access_token, user_id):
    return asyncio.run(fetch_unread_emails(access_token, user_id))

# def mark_as_readOrUnread(access_token: str, user_id: str, message_id: str, isRead: bool = True) -> None:
#     asyncio.run(mark_as_read(access_token, user_id, message_id) if isRead else mark_as_unread(access_token, user_id, message_id))

def forward_email_sync(access_token, user_id, message_id, original_sender, forward_to, forwardMsg="Forwarded message"):
    asyncio.run(forward_email(access_token, user_id, message_id, original_sender, forward_to, forwardMsg))