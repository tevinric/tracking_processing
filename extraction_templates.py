available_tempates = ['amberconnect','beame','bidvest','cartrack','ctrack','fidelity','netstar','pfkelectronics','tracker']

templates = {
    "amberconnect": {
        "system_prompt": "amberconnect_template",
        "user_prompt": "Amberconnect template"
    },
    "beame": {
        "template": "beame_template",
        "description": "Beame template"
    },
    "bidvest": {
        "template": "bidvest_template",
        "description": "Bidvest template"
    },
    "cartrack": {
        "template": "cartrack_template",
        "description": "Cartrack template"
    },
    "ctrack": {
        "template": "ctrack_template",
        "description": "Ctrack template"
    },
    "fidelity": {
        "template": "fidelity_template",
        "description": "Fidelity template"
    },
    "netstar": {
        "system_prompt": """You are a helpful AI extraction assistant. Your role is to analyse the email context that is provided by the user and extract the following information from the email context:
                            1. VIN number (also reffered to as the Chassis number)
                            2. Engine number
                            3. Registration number
                            4. Asset year (also reffered to as the vehicle year)
                            5. Asset make (also reffered to as the vehicle make)
                            6. Asset model (also reffered to as the vehicle model)
                            7. Contract Number (as per the netstar fitment certificate details)
                            8. Fitment Date (also know as the installation_date) in format YYYY-MM-DD
                            9. Product name, also sometime reffered to as VBU. This is the decription of the name of product that was fitted to the vehicle.
                            
                            
                            If a required field is not found in the provided context, you must return "not_found" as the value for that field.
                            You must reponse in the following JSON format:
                            {
                                "vin_number": "answer",
                                "engine_number": "answer",
                                "registration_number": "answer",
                                "vehicle_year": "answer",
                                "vehicle_make": "answer",
                                "vehicle_model": "answer",
                                "contract_number": "answer",
                                "fitment_date": "answer",
                                "product_name": "answer"
                            }
                            """,
        "description": "Netstar template"
    },
    "pfkelectronics": {
        "template": "pfkelectronics_template",
        "description": "Pfkelectronics template"
    },
    "tracker": {
        "template": "tracker_template",
        "description": "Tracker template"
    }
}
