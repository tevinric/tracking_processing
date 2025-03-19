import os

# AZURE OPENAI CONNECTION DETAILS
AZURE_OPENAI_KEY=os.environ.get('AZURE_OPENAI_KEY')
AZURE_OPENAI_ENDPOINT=os.environ.get('AZURE_OPENAI_ENDPOINT')

# SQL SERVER CONNECTIONS
# SQL_SERVER = os.environ.get('SQL_SERVER')
# SQL_DATABASE = os.environ.get('SQL_DATABASE')
# SQL_USERNAME = os.environ.get('SQL_USERNAME')
# SQL_PASSWORD = os.environ.get('SQL_PASSWORD')

#MICROSOFT GRAPH API CONFIGS
MS_CLIENT_ID = os.environ.get('MS_CLIENT_ID')
TENANT_ID = os.environ.get('TENANT_ID')
MS_CLIENT_SECRET = os.environ.get('MS_CLIENT_SECRET')
AUTHORITY = f'https://login.microsoftonline.com/{TENANT_ID}'
SCOPE = ['https://graph.microsoft.com/.default']

# Azure Document Intelligence Configuration
AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=https://your-document-intelligence-resource.cognitiveservices.azure.com/
AZURE_DOCUMENT_INTELLIGENCE_KEY=your_document_intelligence_api_key

# EMAIL CONFIGURATIONS
EMAIL_ACCOUNTS = [os.environ.get('EMAIL_ACCOUNT')]
DEFAULT_EMAIL_ACCOUNT = 'tevinri@tihsa.co.za'

# INTERVAL IN SECONDS(30) 
EMAIL_FETCH_INTERVAL = 30
