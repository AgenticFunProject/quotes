targetScope = 'resourceGroup'

@description('Azure region for the deployed resources.')
param location string = resourceGroup().location

@description('Short environment label used for tagging.')
param envName string = 'prod'

@description('Globally unique resource name prefix supplied by the workflow.')
param namePrefix string

@description('Starter container image used until the first application deploy updates the web app.')
param containerImage string = 'mcr.microsoft.com/azuredocs/aci-helloworld'

@description('Port exposed by the containerized application.')
param containerPort int = 8000

@description('SQLite database location on the App Service persistent filesystem.')
param databaseUrl string = 'sqlite:////home/site/data/quotes.db'

var appServicePlanName = 'asp-${namePrefix}'
var webAppName = 'app-${namePrefix}'
var appInsightsName = 'appi-${namePrefix}'
var containerRegistryName = toLower(replace('acr${namePrefix}', '-', ''))
var acrPullRoleDefinitionId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')

resource appServicePlan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: appServicePlanName
  location: location
  sku: {
    name: 'B1'
    tier: 'Basic'
  }
  kind: 'linux'
  properties: {
    reserved: true
  }
  tags: {
    environment: envName
    managedBy: 'github-actions'
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
  }
  tags: {
    environment: envName
    managedBy: 'github-actions'
  }
}

resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: containerRegistryName
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
  }
  tags: {
    environment: envName
    managedBy: 'github-actions'
  }
}

resource webApp 'Microsoft.Web/sites@2023-12-01' = {
  name: webAppName
  location: location
  kind: 'app,linux,container'
  httpsOnly: true
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: appServicePlan.id
    siteConfig: {
      linuxFxVersion: 'DOCKER|${containerImage}'
      alwaysOn: true
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      healthCheckPath: '/health'
      acrUseManagedIdentityCreds: true
      appSettings: [
        {
          name: 'WEBSITES_PORT'
          value: string(containerPort)
        }
        {
          name: 'WEBSITES_CONTAINER_START_TIME_LIMIT'
          value: '1800'
        }
        {
          name: 'DATABASE_URL'
          value: databaseUrl
        }
        {
          name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
          value: appInsights.properties.ConnectionString
        }
      ]
    }
  }
  tags: {
    environment: envName
    managedBy: 'github-actions'
  }
}

resource acrPullAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: containerRegistry
  name: guid(containerRegistry.id, webApp.id, acrPullRoleDefinitionId)
  properties: {
    roleDefinitionId: acrPullRoleDefinitionId
    principalId: webApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

output resourceGroupName string = resourceGroup().name
output webAppName string = webApp.name
output webAppUrl string = 'https://${webApp.properties.defaultHostName}'
output containerRegistryName string = containerRegistry.name
output containerRegistryLoginServer string = containerRegistry.properties.loginServer
output appServicePlanName string = appServicePlan.name
