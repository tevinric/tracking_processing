import requests
import os
import json
import uuid
from openai import AzureOpenAI
from config import AZURE_OPENAI_KEY, AZURE_OPENAI_ENDPOINT

base_url = os.environ.get('base_url')
client_id = os.environ.get('client_id')
client_secret = os.environ.get('client_secret')
scope = os.environ.get('scope')

# CREATE AN OPENAI CONNECTION
def get_openai_client():
    client = AzureOpenAI(
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_key=AZURE_OPENAI_KEY,
    api_version="2024-02-01",
)
    return client


def get_tracking_company(llm_text):
    client = get_openai_client()
    
    response =  client.chat.completions.create(
    model='gpt-4o',
    messages=[
        {
            "role": "system", 
            "content": """
                You are a helpful AI classification assistant. Your role is to analyse the email context that is provided by the user and classify the email context according to the tracker company mentioned in the email.
                You must strictlty classify the email context into one of the following tracking companies. 
                1. amberconnect
                2. beame
                3. bidvest
                4. cartrack
                5. ctrack
                6. fidelity
                7. netstar
                8. pfkelectronics
                9. tracker
                10. other
                
                You may only use "other" classification if the email context does not match any of the above tracking companies.
                
                You must use the provided email context (subject line, email body and attachments text) to classify the email context.
                
                You must reponse in the following JSON format:
                {"tracker_company": "answer"}
            """
        },
        {
            "role": "user",
            "content": f"Analyse the following email context to idenifty the tracking company: {llm_text}"
        }
    ],
    temperature=0.1,
    response_format={"type": "json_object"}        
    )
    
    return response


def get_id_number(llm_text):
    client = get_openai_client()
    
    response =  client.chat.completions.create(
    model='gpt-4o-mini',
    messages=[
        {
            "role": "system", 
            "content": """
                You are a helpful AI data extraction assistant. Your role is to analyse the email context that is provided by the user and extract the South African Identity Number from the email. 
                Take note of the following of characteristics of a typical South African Identiity Number:
                1. A South African Identity Number is always a 13 digit numeric number
                2. The first 6 digits of the identity number represent the date of birth in the format YYMMDD
                3. The SA ID number may be found in the email subject line, email body or the attachements extracted text.               
                
                If a valid South African ID number is not found in the provided context, you must return "not_found" as the id_number.
                
                You must reponse in the following JSON format:
                {"id_number": "answer"}
            """
        },
        {
            "role": "user",
            "content": f"Analyse the following email context to extract the policy number: {llm_text}"
        }
    ],
    temperature=0.1,
    response_format={"type": "json_object"}        
    )
    
    return response


def get_policy_number(llm_text):
    client = get_openai_client()
    
    response =  client.chat.completions.create(
    model='gpt-4o-mini',
    messages=[
        {
            "role": "system", 
            "content": """
                You are a helpful AI data extraction assistant. Your role is to analyse the email context that is provided by the user and extract the company policy number from the email. 
                Take note of the following of characteristics of the policy number:
                1. A policy number is always a 9 digit numeric number
                2. The policy number may be found in the email subject line or email body
                3. The policy number may be found at any point in the email trail
                4. The policy is a unique identifer that links to a customer's insurance policy
                
                
                If a policy number is not found in the email context, you must return "not_found" as the policy number.
                
                You must reponse in the following JSON format:
                {"policy_number": "answer"}
            """
        },
        {
            "role": "user",
            "content": f"Analyse the following email context to extract the policy number: {llm_text}"
        }
    ],
    temperature=0.1,
    response_format={"type": "json_object"}        
    )
    
    return response


def extract_details(llm_text, template):
    client = get_openai_client()
    
    response =  client.chat.completions.create(
    model='gpt-4o',
    messages=[
        {
            "role": "system", 
            "content": template["system_prompt"]
        },
        {
            "role": "user",
            "content": f"Analyse the following email context to extract the request details from the attachements text: {llm_text}"
        }
    ],
    temperature=0.1,
    response_format={"type": "json_object"}        
    )
    
    return response



# FUNCTION TO GENERATE A VALID TOKEN
def get_token():
    url = f"{base_url}/token"
    payload = f"grant_type=client_credentials&client_id={client_id}&client_secret={client_secret}&scope={scope}"
    headers = {
    'Content-Type': 'application/x-www-form-urlencoded',
    'Cookie': ''
    }
    response = requests.request("GET", url, headers=headers, data=payload)
    token = response.json()['access_token']
    
    return token

# FUNCTION TO GET ACTIVE POLICIES BY IDNUMBER

def get_active_policies(id_number,token):
    """_summary_

    Args:
        id_number (str): Customer ID number to search for linked actuve policy numbers
        token (str): Authentication token generated by the KONG authentication server
        
    Returns:
        response (json): A JSON object containing the response code, a list of active policies and ava-correlation-id
    
    """
    url = f"{base_url}/esb/api/v2/persons/{id_number}/details?type=IDNUMBER"
    payload = ""
    ava_correlation_id = f"ava-{str(uuid.uuid4())}"
    headers = {
    'Authorization': f"Bearer {token}",
    'correlationId': ava_correlation_id, #Generate a unique correlation ID for ava-record
    'Cookie': ""
    }

    response = requests.request("GET", url, headers=headers, data=payload)

    # Initialize an empty list to store active policy reference numbers  
    activePolicies = [] 
    
    if response.status_code == 200:
        response_code = response.status_code
        data = response.json()
    
        # Iterate through each client detail  
        for client in data['clientDetails']:  
            # Check if 'statusDescription' contains the word 'active' (case insensitive)  
            if 'active' in client['statusDescription'].lower():  
                activePolicies.append(client['referenceNumber'])  
    

    else:
        response_code = response.status_code
        print(f"Failed to retrieve data: {response.status_code}")

    output_response = {
        "response_code": response_code,
        "activePolicies": activePolicies,
        "correlationId": ava_correlation_id
    }
    
    return output_response


def get_vehicles(token, policyNumber):
    """_summary_

    Args:
        policy_number (str): Policy number to search for policy details
    """
    
    import requests

    url = f"{base_url}/esb/api/v1/policies/{policyNumber}/detail?filter=vehicle"

    correlation_id = f"ava-{str(uuid.uuid4())}"
    
    payload = ""
    headers = {
    'Authorization': f"Bearer {token}",
    'correlationId': correlation_id,
    'Cookie': ''
    }

    response = requests.request("GET", url, headers=headers, data=payload)
    
    data = response.json()
    policyDetails = data["policyDetailResponse"]
    vehicleDetails = policyDetails[0]["vehicleDetailsArray"]
    vehicles = {}
    for vehicle in vehicleDetails:
        if vehicle["statusDescription"].strip() != "": 
            # Prepare the vehicle details dictionary
            vehicleDetailValues = {"year": vehicle["year"],
                                    "make": vehicle["make"],
                                    "model": vehicle["model"],
                                    "colour": vehicle["colour"],
                                    "registrationNumber": vehicle["registrationNumber"],
                                    "vinNumber": vehicle["vinNumber"],
                                    "engineNumber": vehicle["engineNumber"],
                                    "riskItemSequenceNumber": vehicle["riskItemSequenceNumber"],
                                    "coverTypeDescription": vehicle["coverTypeDescription"],
                                    "statusDescription": vehicle["statusDescription"],
                                    "vehicleActiveIndicator": vehicle["vehicleActiveIndicator"]
                                    }
            
            vehicle = {int(vehicle["riskItemSequenceNumber"]): vehicleDetailValues}
            
            vehicles.update(vehicle)
            
    return vehicles
    
    
from sentence_transformers import SentenceTransformer, util
from sklearn.metrics.pairwise import cosine_similarity

def text_similarity_score(text1,text2,model):
    """
    Compute a semantic similarity score between two texts using cosine similarity.
    :param text1: The first text string
    :param text2: The second text string
    :param model: A loaded SentenceTransformer model
    :return: A float simialrity score between 0 and 1
    """
    
    #Get the embeddings for both texts
    embeddings = model.encode([text1, text2])
    
    # Compute cosine similariyt between the two embeddings
    score = cosine_similarity([embeddings[0]],[embeddings[1]])[0][0]
    
    return score 
