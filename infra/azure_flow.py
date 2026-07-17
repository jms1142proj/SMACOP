
#####################
# This automation script still have idempotence issues, ensure resources from previous runs are properly removed before running to prevent unintended errors

# App Service Plan has throttling behavior for repeated remove/create actions, consider creating a separate persistent rg and reuse it between run
######################
import os
import ipaddress
import json

from util import run_command

APP_SERVICE_SKU = 'B1'
ACR_SKU = 'Basic'
MANAGED_IDENTITY_ACR_CONFIG = '{"acrUseManagedIdentityCreds": true}'
LOCATION = 'canadaeast'
APP_SERVICE_LOCATION = "centralus"
PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

WEB_APP_DIR = os.path.join(
    PROJECT_ROOT,
    "azure",
    "web-app"
)

def authenticate():
    # Authenticate the python automation script with azure using service principal
    # Can be skipped in run manually from local machine
    pass

def create_resource_group(rg_name, location):
    create_rg_cmd = ["az", "group", "create", "--name", rg_name, "--location", location, "--output", "table"]
    run_command(create_rg_cmd)

def create_vm(
        rg_name, 
        vm_name, 
        location, 
        nsg_name=None, 
        shutdown_time="2100"
    ):

    if nsg_name is None:
        nsg_name = f"{vm_name}-NSG"

    ssh_key_path = os.path.expanduser(f"~/.ssh/{rg_name}_{vm_name}_key")
    source_bootstrap_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bootstrap_vm.sh")

    if not os.path.exists(ssh_key_path):
        generate_ssh_key_cm = [
            "ssh-keygen", 
            "-t", "rsa", 
            "-b", "4096",
            "-f", ssh_key_path, 
            "-N", ""]  # Generate SSH key pair for the VM
        run_command(generate_ssh_key_cm)
    else:
        print(f"SSH key already exists: {ssh_key_path}")

    check_vm_cmd = ["az", "vm", "list", "-g", rg_name, "--query", f"[?name=='{vm_name}'].name", "-o", "tsv"]
    vm_check_output = run_command(check_vm_cmd).strip()

    if not vm_check_output:
        print(f"VM {vm_name} not found. Provisioning now...")
        create_vm_cmd = [
            "az", "vm", "create", 
            "--resource-group", rg_name,
            "--name", vm_name,
            "--nsg", nsg_name,
            "--image", "Ubuntu2204",
            "--size", "Standard_B2ats_v2",
            "--storage-sku", "Standard_LRS",
            "--boot-diagnostics-storage", "",
            "--admin-username", "azureuser",
            "--ssh-key-values", f"{ssh_key_path}.pub",
            "--location", location,
            "--output", "table"
        ]
        run_command(create_vm_cmd)

    auto_shutdown_cmd = [
        "az", "vm", "auto-shutdown", 
        "-g", rg_name, 
        "-n", vm_name, 
        "--time", shutdown_time,
        "-o", "none"]
    run_command(auto_shutdown_cmd)

def deploy_app_to_vm_via_bootstrap_script(
        vm_public_ip,
        ssh_key_path, 
        source_bootstrap_path
    ):
    
    # SCP bootstrap script to remote VM
    print(f"=== Copying Bootstrap Script to Remote VM ({vm_public_ip}) ===")
    scp_cmd = [
        "scp",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-i", ssh_key_path,
        source_bootstrap_path,
        f"azureuser@{vm_public_ip}:~/"
    ]
    run_command(scp_cmd)
    print()

    # SSH and run the remote bootstrap script to set up Docker, Docker Compose, and deploy the FastAPI application
    print("=== SSH into VM and Execute Bootstrap Script ===")
    ssh_cmd = [
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-i", ssh_key_path,
        f"azureuser@{vm_public_ip}",
        "sudo bash ~/bootstrap_vm.sh"
    ]
    run_command(ssh_cmd, print_result=False)
    print()

def create_azure_web_app(rg_name, app_service_name, web_app_name):
    # Create an app service plan, --sku F1 --is-linux
    # Create a web app with the above plan

    app_servie_plan_cmd = [
        "az", "appservice", "plan", "create",
        "--name", app_service_name,
        "--resource-group", rg_name,
        "--sku", "F1",
        "--is-linux"
    ]
    run_command(app_servie_plan_cmd)

    azure_web_app_cmd = [
        "az", "webapp", "create",
        "--name", web_app_name,
        "--resource-group", rg_name,
        "--plan", app_service_name,
        "--runtime", "PYTHON|3-12"
    ]
    run_command(azure_web_app_cmd)

def create_acr(rg_name, acr_name, sku):

    register_provider_cmd = [
        "az", "provider", "register",
        "--namespace", "Microsoft.ContainerRegistry",
        "--wait"
    ]
    run_command(register_provider_cmd)

    acr_cmd = [
        "az", "acr", "create",
        "--resource-group", rg_name,
        "--name", acr_name,
        "--sku", sku
    ]
    run_command(acr_cmd)

def build_locally_and_push_image_to_acr(
        acr_name, 
        image_name,
        image_tag="latest"
    ):
    
    acr_login_cmd = [
        "az", "acr", "login",
        "--name", acr_name
    ]
    run_command(acr_login_cmd)

    acr_show_login_server_cmd = [
        "az", "acr", "show",
        "--name", acr_name,
        "--query", "loginServer",
        "--output", "tsv"
    ]
    login_server = run_command(acr_show_login_server_cmd).strip()
    container_image = f"{login_server}/{image_name}:{image_tag}"

    docker_build_cmd = [
        "docker", "build",
        "-t", container_image,
        WEB_APP_DIR
    ]
    run_command(docker_build_cmd)

    docker_push_cmd = [
        "docker", "push",
        container_image,
    ]
    run_command(docker_push_cmd)

    return container_image

def create_empty_web_app_with_managed_identity(
        rg_name, 
        location, 
        app_service_plan_name,
        web_app_name, 
        container_image,
        sku=APP_SERVICE_SKU
    ):
    
    # TOO MANY REMOVE/CREATE CYCLE WILL GET THROTTLED
    appservice_plan_create_cmd = [
        "az", "appservice", "plan", "create",
        "--name", app_service_plan_name,
        "--resource-group", rg_name,
        "--location", location,
        "--sku", sku,
        "--is-linux"
    ]
    run_command(appservice_plan_create_cmd)

    web_app_create_cmd = [
        "az", "webapp", "create",
        "--resource-group", rg_name,
        "--plan", app_service_plan_name,
        "--name", web_app_name,
        "--container-image-name", container_image,
        "--output", "none"
    ]
    run_command(web_app_create_cmd)

    identity_assign_cmd = [
        "az", "webapp", "identity", "assign",
        "--resource-group", rg_name,
        "--name", web_app_name,
        "--output", "none"
    ]
    run_command(identity_assign_cmd)

    webapp_enable_acr_managed_identity_cmd = [
        "az", "webapp", "config", "set",
        "--resource-group", rg_name,
        "--name", web_app_name,
        "--generic-configurations", MANAGED_IDENTITY_ACR_CONFIG,
    ]
    run_command(webapp_enable_acr_managed_identity_cmd)

def deploy_container_to_azure_web_app(
        rg_name, 
        acr_name, 
        location, 
        app_service_plan_name, 
        web_app_name, 
        appservice_sku,
        image_name,
        image_tag,
        container_port,
        acr_sku
    ):
    # Create an ACR
    # Deploy as a quick task
        # Utilize az acr build to let ACR build and push image to the ACR
        # Create Azure Web App pointing to the image on the ACR 
    
    create_rg_cmd = [
        "az", "group", "create", 
        "--name", rg_name, 
        "--location", location, 
        "--output", "table"
    ]
    run_command(create_rg_cmd)

    create_acr(rg_name, acr_name, acr_sku)
    container_image = build_locally_and_push_image_to_acr(acr_name, image_name, image_tag)

    app_service_location = APP_SERVICE_LOCATION
    create_empty_web_app_with_managed_identity(rg_name, app_service_location, app_service_plan_name, web_app_name, container_image, appservice_sku)

    webapp_identity_show_cmd = [
        "az", "webapp", "identity", "show",
        "--resource-group", rg_name,
        "--name", web_app_name,
        "--query", "principalId",
        "--output", "tsv"
    ]
    principal_id = run_command(webapp_identity_show_cmd).strip()

    acr_show_id_cmd = [
        "az", "acr", "show",
        "--name", acr_name,
        "--query", "id",
        "--output", "tsv"
    ]
    acr_id = run_command(acr_show_id_cmd).strip()

    acr_pull_role_assignment_cmd = [
        "az", "role", "assignment", "create",
        "--assignee", principal_id,
        "--role", "AcrPull",
        "--scope", acr_id
    ]
    run_command(acr_pull_role_assignment_cmd)

    webapp_container_set_cmd = [
        "az", "webapp", "config", "container", "set",
        "--name", web_app_name,
        "--resource-group", rg_name,
        "--container-image-name", container_image
    ]
    run_command(webapp_container_set_cmd)

    port_config_cmd = [
        "az", "webapp", "config", "appsettings", "set",
        "--resource-group", rg_name,
        "--name", web_app_name,
        "--settings", f"WEBSITES_PORT={container_port}",
        "--output", "none"
    ]
    run_command(port_config_cmd)

    webapp_restart_cmd = [
        "az", "webapp", "restart",
        "--resource-group", rg_name,
        "--name", web_app_name
    ]
    run_command(webapp_restart_cmd)

    # ==================================
    # Deploy as triggered task (EXTRA)
        # Utilize az acr create task, specifying the dockerfile in github /azure devops repo
        # Setup PAT for the task in Github/Azure Devops repo
        # Create Azure Web App pointing to the image on the ACR and enable Continuous Deployment
        # FLOW: Commit -> ACR build, update image, and send webhook to Azure Web App -> Azure Web App pull new image and restart container

def create_nsg_rule():
    pass

def create_vnet():
    pass

def create_subnet():
    pass

def create_service_endpoint():
    pass

def get_private_endpoint_subnet_prefix(
    rg_name,
    vnet_name
):
    
    vnet_show_cmd = [
        "az", "network", "vnet", "show",
        "--resource-group", rg_name,
        "--name", vnet_name,
        "--query", "addressSpace.addressPrefixes[0]",
        "--output", "tsv"
    ]

    vnet_prefix = run_command(vnet_show_cmd).strip()
    vnet_network = ipaddress.ip_network(vnet_prefix)

    if not isinstance(vnet_network, ipaddress.IPv4Network):
        raise ValueError("Only IPv4 VNets are supported.")

    octets = str(vnet_network.network_address).split(".")
    private_endpoint_prefix = (
        f"{octets[0]}.{octets[1]}.10.0/24"
    )

    private_endpoint_network = ipaddress.ip_network(
        private_endpoint_prefix
    )

    if not private_endpoint_network.subnet_of(vnet_network):
        raise ValueError(
            f"{private_endpoint_prefix} is outside "
            f"the VNet address space {vnet_prefix}."
        )

    return private_endpoint_prefix

def create_private_endpoint_for_web_app(   
    rg_name,
    vm_rg_name,
    location,
    vnet_name,
    web_app_name
):
    # Create a subnet for private endpoint
    # Create the private endpoint
    # Create the DNS zone & link it to the vnet
    # Create the DNS zone group between DNS zone and private endpoint to opt-in to Azure's automatic DNS management

    private_endpoint_subnet_name = (
        input("Private endpoint subnet name [private-endpoint-subnet]: ")
        or "private-endpoint-subnet"
    )

    private_endpoint_subnet_prefix = (
        get_private_endpoint_subnet_prefix(
            vm_rg_name,
            vnet_name,
        )
    )

    private_endpoint_name = (
        input("Private endpoint name [p1-private-endpoint]: ")
        or "p1-private-endpoint"
    )

    private_connection_name = (
        input("Private connection name [web-app-connection]: ")
        or "web-app-connection"
    )

    private_dns_zone = (
        input("Private DNS zone [privatelink.azurewebsites.net]: ")
        or "privatelink.azurewebsites.net"
    )

    private_dns_link_name = (
        input("Private DNS link name [appservice-dns-link]: ")
        or "appservice-dns-link"
    )

    dns_zone_group_name = (
        input("DNS zone group name [default]: ")
        or "default"
    )

    # NEED ADDITIONAL CHECK FOR IDEMPOTENCY
    subnet_create_cmd = [
        "az", "network", "vnet", "subnet", "create",
        "--resource-group", rg_name,
        "--vnet-name", vnet_name,
        "--name", private_endpoint_subnet_name,
        "--address-prefixes", private_endpoint_subnet_prefix
    ]
    run_command(subnet_create_cmd)
    
    webapp_show_id_cmd = [
        "az", "webapp", "show",
        "--resource-group", rg_name,
        "--name", web_app_name,
        "--query", "id",
        "--output", "tsv"
    ]
    web_app_resource_id = run_command(webapp_show_id_cmd).strip()

    private_endpoint_create_cmd = [
        "az", "network", "private-endpoint", "create",
        "--name", private_endpoint_name,
        "--location", location,
        "--resource-group", vm_rg_name,
        "--vnet-name", vnet_name,
        "--subnet", private_endpoint_subnet_name,
        "--private-connection-resource-id", web_app_resource_id,
        "--group-ids", "sites",
        "--connection-name", private_connection_name
    ]
    run_command(private_endpoint_create_cmd)

    private_dns_zone_create_cmd = [
        "az", "network", "private-dns", "zone", "create",
        "--resource-group", vm_rg_name,
        "--name", private_dns_zone
    ]
    run_command(private_dns_zone_create_cmd)

    private_dns_link_create_cmd = [
        "az", "network", "private-dns", "link", "vnet", "create",
        "--resource-group", vm_rg_name,
        "--zone-name", private_dns_zone,
        "--name", private_dns_link_name,
        "--virtual-network", vnet_name,
        "--registration-enabled", "false",
    ]
    run_command(private_dns_link_create_cmd)

    dns_zone_group_create_cmd = [
        "az", "network", "private-endpoint", "dns-zone-group", "create",
        "--resource-group", vm_rg_name,
        "--endpoint-name", private_endpoint_name,
        "--name", dns_zone_group_name,
        "--private-dns-zone", private_dns_zone,
        "--zone-name", private_dns_zone
    ]
    run_command(dns_zone_group_create_cmd)

    disable_public_access_cmd = [
        "az", "resource", "update",
        "--resource-group", rg_name,
        "--name", web_app_name,
        "--resource-type", "Microsoft.Web/sites",
        "--set", "properties.publicNetworkAccess=Disabled"
    ]
    run_command(disable_public_access_cmd)

def create_log_analytics_workspace():
    pass

def create_azure_managed_grafana():
    # Create grafana workspace
    # Grant 
    pass

def start_deployment():
    rg_name = input("Resource group [p1-rg]: ") or "p1-rg"
    vm_rg_name = input("Resource group [project-01]: ") or "project-01"
    location = input(f"Location [{LOCATION}]: ") or LOCATION
    acr_name = input("ACR name [p1acr]: ") or "p1acr"
    app_service_plan_name = (
        input("App Service Plan [p1-app-service-plan]: ")
        or "p1-app-service-plan"
    )
    app_vnet_name = input("VNet name [vnet-canadaeast-1]: ") or "vnet-canadaeast-1" 
    web_app_name = input("Web App name [p1-web-app]: ") or "p1-web-app"
    image_name = input("Image name [p1-api]: ") or "p1-api"
    image_tag = input("Image tag [latest]: ") or "latest"

    # 1. Authenticate the script
    # 2. Deploy container app to Azure Web App
    # 3. Provision monitoring resources
        # Set up 
        # Set up Grafana to query from LAW using KQL
    # =========================================

    # 1.
    # For simplicity, perform manually with az login 
    # authenticate()

    # 2.
    # create_resource_group()
    # create_vnet()
    # create nsg rules for the vnet
    # create and deploy authentication app to vm
    
    deploy_container_to_azure_web_app(
        rg_name=rg_name,
        acr_name=acr_name,
        location=location,
        app_service_plan_name=app_service_plan_name,
        web_app_name=web_app_name,
        appservice_sku=APP_SERVICE_SKU,
        image_name=image_name,
        image_tag=image_tag,
        container_port=8081,
        acr_sku=ACR_SKU
    )

    create_private_endpoint_for_web_app(
        rg_name=rg_name,
        vm_rg_name=vm_rg_name,
        location=location,
        vnet_name=app_vnet_name,
        web_app_name=web_app_name
    )

    # 3. 
    # create_resource_group()
    # create_log_analytics_workspace()
    # create_application_insights(), 
        # for app telemetry, utilize SDK in code  
        # for connection string injection, enable in web app settings
    # configure_diagnostics_settings() (for platform logs)
    # create_azure_managed_grafana()

if __name__ == '__main__':
    start_deployment()
