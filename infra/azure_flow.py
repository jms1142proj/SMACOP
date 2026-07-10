

def authenticate():
    # Authenticate the python automation script with azure using service principal
    pass

def create_resource_group():
    pass

def create_vm():
    pass

def create_azure_web_app():
    # Create an app service plan, --sku F1 --is-linux
    # Create a web app with the above plan
    pass

def create_acr():
    pass

def create_nsg():
    pass

def create_vnet():
    pass

def create_subnet():
    pass

def create_service_endpoint():
    pass

def create_private_endpoint():
    # Create a subnet for private endpoint
    # Create the private endpoint
    # Create the DNS zone & link it to the vnet
    # Create the DNS zone group between DNS zone and private endpoint to opt-in to Azure's automatic DNS management
    pass

def create_azure_monitor():
    pass

def create_log_analytics_workspace():
    pass

def create_grafana_dashboard():
    pass

def deploy_container_to_azure_web_app():
    # Create an ACR
    # Deploy as a quick task
        # Utilize az acr build to let ACR build and push image to the ACR
        # Create Azure Web App pointing to the image on the ACR 
    
    # ==================================
    # Deploy as triggered task (EXTRA)
        # Utilize az acr create task, specifying the dockerfile in github /azure devops repo
        # Setup PAT for the task in Github/Azure Devops repo
        # Create Azure Web App pointing to the image on the ACR and enable Continuous Deployment
        # FLOW: Commit -> ACR build, update image, and send webhook to Azure Web App -> Azure Web App pull new image and restart container

    pass

def start_deployment():
    # 1. Authenticate the script
    # 2. Deploy container app to Azure Web App
    # 3. Provision monitoring resources
    # =========================================

    # 1. 
    authenticate()

    # 2.
    # create_resource_group()
    # create_vnet()
    # create nsg rules for the vnet
    # 
    # 
    # deploy_container_to_azure_web_app()
    # create_private_endpoint() for the azure web app

    # 3. 
    pass