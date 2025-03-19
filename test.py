import requests
import os
import json
import uuid

import functions as func

id_number = "7507195335085"

# Generate a token
token =func.get_token()

# Get the list of active policies

response = func.get_active_policies(id_number,token)

if response["response_code"] == 200:
    activePolices = response["activePolicies"]
    correlationId = response["correlationId"]
    print(activePolices)
else:
    # Handle errors for failed requests for activePolicy numbers
    pass

# Get the details of the active policies

for policyNumber in activePolices:
    response = func.get_vehicles(token, policyNumber)
    
    print(response)


