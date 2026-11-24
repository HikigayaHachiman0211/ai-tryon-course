targetScope = 'resourceGroup'

@description('Azure region for all resources (must support ACA + PostgreSQL Flexible Server + Storage)')
param location string = resourceGroup().location

@description('Short unique prefix for naming resources (lowercase alphanumeric, 3-10 chars)')
@minLength(3)
@maxLength(10)
param namePrefix string = 'tryon'

@description('Unique suffix appended to globally unique names (ACR, Storage, PostgreSQL, Key Vault)')
@minLength(4)
@maxLength(10)
param uniqueSuffix string = take(uniqueString(resourceGroup().id), 8)

@description('Container image tag to deploy (built during release packaging)')
param imageTag string = 'latest'

@description('Optional image tag override for Admin service only (defaults to imageTag when empty)')
param adminImageTag string = ''

@description('PostgreSQL administrator username')
param pgAdminUser string = 'tryonadmin'

@secure()
@description('PostgreSQL administrator password (set in Key Vault / CI parameters, never commit real secrets)')
param pgAdminPassword string

@secure()
@description('Fernet encryption key for Admin AI provider secrets (shared across Admin & Workbench/Worker)')
param fernetSecretKey string

@secure()
@description('Admin JWT signing key')
param jwtSecretKey string

@secure()
@description('Shared internal ingest/retry secret key between Main, Workbench, and Admin')
param ingestSecretKey string

@secure()
@description('Short-lived signed media / task token secret shared across replicas')
param taskTokenSecret string

@description('Bootstrap Admin username')
param adminInitUsername string = 'admin'

@secure()
@description('Bootstrap Admin password')
param adminInitPassword string

@secure()
@description('Optional Admin recovery key for self-service forgot-password reset')
param adminRecoveryKey string = ''

@description('Optional exact public URL overrides after initial provisioning (comma-separated CORS origins)')
param corsAllowOrigins string = ''

@description('Storage container names (product-images uses Blob public read by default for CDN/direct browser caching; course-media stays private)')
param productContainerName string = 'product-images'
param mediaContainerName string = 'course-media'
param queueName string = 'tryon-tasks'
param pgDatabaseName string = 'ai_tryon'

@description('Set false on phase 1 to provision ACR, Storage, PostgreSQL, Key Vault, RBAC, and ACA environment before images exist in ACR')
param deployWorkloads bool = true

@description('Allow anonymous read on product-images container only (course-media always remains None)')
param allowBlobPublicAccess bool = true

@description('Optional override for PUBLIC_IMAGE_BASE_URL (defaults to direct Blob product-images URL when allowBlobPublicAccess is true)')
param publicImageBaseUrl string = ''

@description('Log Analytics daily cap in GB to stay within the 5 GB/month free ingestion allowance')
param logDailyQuotaGb string = '0.1'

@description('Container Registry SKU (Basic or Standard)')
@allowed([
  'Basic'
  'Standard'
])
param acrSku string = 'Basic'

@description('Admin app vCPU / memory allocation')
param adminCpu string = '0.25'
param adminMemory string = '0.5Gi'

@description('Direct DB reporting mode for analytics/tasks so idle admin container stays scaled to zero')
param adminReportMode string = 'db'

var acrName = toLower('${namePrefix}acr${uniqueSuffix}')
var storageName = toLower('${namePrefix}st${uniqueSuffix}')
var pgServerName = toLower('${namePrefix}-pg-${uniqueSuffix}')
var kvName = toLower('${namePrefix}-kv-${uniqueSuffix}')
var lawName = '${namePrefix}-law-${uniqueSuffix}'
var acaEnvName = '${namePrefix}-aca-env'
var uamiName = '${namePrefix}-uami'

var mainAppName = '${namePrefix}-main'
var workbenchAppName = '${namePrefix}-workbench'
var adminAppName = '${namePrefix}-admin'
var workerJobName = '${namePrefix}-worker'
var dbInitJobName = '${namePrefix}-db-init'

// Built-in Azure RBAC Role Definition IDs
var roleAcrPull = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
var roleStorageBlobDataContributor = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
var roleStorageQueueDataContributor = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '974c5e8b-45b9-4653-ba55-5f855dd0fb88')
var roleKeyVaultSecretsUser = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')

var databaseUrlValue = 'postgresql+psycopg://${pgAdminUser}:${uriComponent(pgAdminPassword)}@${pgServerName}.postgres.database.azure.com:5432/${pgDatabaseName}?sslmode=require'
var defaultCors = 'https://${mainAppName}.${acaEnv.properties.defaultDomain},https://${workbenchAppName}.${acaEnv.properties.defaultDomain},https://${adminAppName}.${acaEnv.properties.defaultDomain}'
var effectiveCors = empty(corsAllowOrigins) ? defaultCors : corsAllowOrigins
var effectivePublicImageBaseUrl = !empty(publicImageBaseUrl) ? publicImageBaseUrl : (allowBlobPublicAccess ? 'https://${storageName}.blob.${environment().suffixes.storage}/${productContainerName}' : '')

resource uami 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: uamiName
  location: location
}

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: lawName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
    workspaceCapping: {
      dailyQuotaGb: json(logDailyQuotaGb)
    }
  }
}

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  sku: {
    name: acrSku
  }
  properties: {
    adminUserEnabled: false
  }
}

resource acrPullRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, uami.id, roleAcrPull)
  scope: acr
  properties: {
    principalId: uami.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: roleAcrPull
  }
}

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: storageName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    allowBlobPublicAccess: allowBlobPublicAccess
    allowSharedKeyAccess: true
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-01-01' = {
  parent: storageAccount
  name: 'default'
}

resource productContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  parent: blobService
  name: productContainerName
  properties: {
    publicAccess: allowBlobPublicAccess ? 'Blob' : 'None'
  }
}

resource mediaContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  parent: blobService
  name: mediaContainerName
  properties: {
    publicAccess: 'None'
  }
}

resource queueService 'Microsoft.Storage/storageAccounts/queueServices@2023-01-01' = {
  parent: storageAccount
  name: 'default'
}

resource taskQueue 'Microsoft.Storage/storageAccounts/queueServices/queues@2023-01-01' = {
  parent: queueService
  name: queueName
}

resource storageBlobRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, uami.id, roleStorageBlobDataContributor)
  scope: storageAccount
  properties: {
    principalId: uami.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: roleStorageBlobDataContributor
  }
}

resource storageQueueRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, uami.id, roleStorageQueueDataContributor)
  scope: storageAccount
  properties: {
    principalId: uami.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: roleStorageQueueDataContributor
  }
}

resource pgServer 'Microsoft.DBforPostgreSQL/flexibleServers@2023-06-01-preview' = {
  name: pgServerName
  location: location
  sku: {
    name: 'Standard_B1ms'
    tier: 'Burstable'
  }
  properties: {
    version: '16'
    administratorLogin: pgAdminUser
    administratorLoginPassword: pgAdminPassword
    storage: {
      storageSizeGB: 32
    }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
  }
}

resource pgFirewallAzure 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2023-06-01-preview' = {
  parent: pgServer
  name: 'AllowAzureServices'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

resource pgDb 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2023-06-01-preview' = {
  parent: pgServer
  name: pgDatabaseName
}

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: kvName
  location: location
  properties: {
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enabledForTemplateDeployment: true
    sku: {
      family: 'A'
      name: 'standard'
    }
  }
}

resource kvSecretsRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, uami.id, roleKeyVaultSecretsUser)
  scope: keyVault
  properties: {
    principalId: uami.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: roleKeyVaultSecretsUser
  }
}

resource kvDatabaseUrl 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'database-url'
  properties: { value: databaseUrlValue }
}

resource kvFernetKey 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'fernet-secret-key'
  properties: { value: fernetSecretKey }
}

resource kvJwtKey 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'jwt-secret-key'
  properties: { value: jwtSecretKey }
}

resource kvIngestKey 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'ingest-secret-key'
  properties: { value: ingestSecretKey }
}

resource kvTaskTokenSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'task-token-secret'
  properties: { value: taskTokenSecret }
}

resource kvAdminInitPassword 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'admin-init-password'
  properties: { value: adminInitPassword }
}

resource kvAdminRecoveryKey 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!empty(adminRecoveryKey)) {
  parent: keyVault
  name: 'admin-recovery-key'
  properties: { value: adminRecoveryKey }
}

resource acaEnv 'Microsoft.App/managedEnvironments@2026-07-01' = {
  name: acaEnvName
  location: location
  properties: {
    environmentMode: 'WorkloadProfiles'
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

var commonStorageEnv = [
  { name: 'APP_ENV', value: 'production' }
  { name: 'AZURE_CLIENT_ID', value: uami.properties.clientId }
  { name: 'OBJECT_STORAGE_PROVIDER', value: 'azure' }
  { name: 'AZURE_STORAGE_ACCOUNT_NAME', value: storageAccount.name }
  { name: 'AZURE_STORAGE_ACCOUNT', value: storageAccount.name }
  { name: 'AZURE_PRODUCT_CONTAINER', value: productContainerName }
  { name: 'AZURE_MEDIA_CONTAINER', value: mediaContainerName }
  { name: 'AZURE_STORAGE_QUEUE_NAME', value: queueName }
  { name: 'PUBLIC_IMAGE_BASE_URL', value: effectivePublicImageBaseUrl }
]

// 1. tryon-main (Scale-to-zero HTTP API + React SPA)
resource mainApp 'Microsoft.App/containerApps@2024-03-01' = if (deployWorkloads) {
  name: mainAppName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${uami.id}': {} }
  }
  properties: {
    managedEnvironmentId: acaEnv.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8080
        transport: 'http'
      }
      registries: [
        {
          server: acr.properties.loginServer
          identity: uami.id
        }
      ]
      secrets: [
        { name: 'database-url', keyVaultUrl: kvDatabaseUrl.properties.secretUri, identity: uami.id }
        { name: 'fernet-secret-key', keyVaultUrl: kvFernetKey.properties.secretUri, identity: uami.id }
        { name: 'ingest-secret-key', keyVaultUrl: kvIngestKey.properties.secretUri, identity: uami.id }
        { name: 'task-token-secret', keyVaultUrl: kvTaskTokenSecret.properties.secretUri, identity: uami.id }
      ]
    }
    template: {
      scale: {
        minReplicas: 0
        maxReplicas: 3
        rules: [
          {
            name: 'http-concurrency'
            http: {
              metadata: {
                concurrentRequests: '20'
              }
            }
          }
        ]
      }
      containers: [
        {
          name: 'main'
          image: '${acr.properties.loginServer}/${mainAppName}:${imageTag}'
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: concat(commonStorageEnv, [
            { name: 'PORT', value: '8080' }
            { name: 'DATABASE_URL', secretRef: 'database-url' }
            { name: 'FERNET_SECRET_KEY', secretRef: 'fernet-secret-key' }
            { name: 'INGEST_SECRET_KEY', secretRef: 'ingest-secret-key' }
            { name: 'USER_PHOTO_TOKEN_SECRET', secretRef: 'task-token-secret' }
            { name: 'ENABLE_DEBUG_PAGES', value: 'false' }
            { name: 'RUN_STARTUP_DB_INIT', value: 'false' }
            { name: 'FORCE_PRIVATE_USER_PHOTOS', value: 'true' }
            { name: 'ADMIN_REPORT_MODE', value: adminReportMode }
            { name: 'CORS_ALLOW_ORIGINS', value: effectiveCors }
            { name: 'TRYON_WORKBENCH_URL', value: 'https://${workbenchAppName}.${acaEnv.properties.defaultDomain}' }
          ])
          probes: [
            {
              type: 'Startup'
              httpGet: { path: '/health', port: 8080 }
              initialDelaySeconds: 5
              periodSeconds: 5
              failureThreshold: 12
            }
            {
              type: 'Readiness'
              httpGet: { path: '/health', port: 8080 }
              periodSeconds: 10
            }
          ]
        }
      ]
    }
  }
  dependsOn: [acrPullRole, storageBlobRole, kvSecretsRole]
}

// 2. tryon-workbench (Scale-to-zero API & static frontend; submits tasks to Azure Storage Queue)
resource workbenchApp 'Microsoft.App/containerApps@2024-03-01' = if (deployWorkloads) {
  name: workbenchAppName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${uami.id}': {} }
  }
  properties: {
    managedEnvironmentId: acaEnv.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8080
        transport: 'http'
      }
      registries: [
        {
          server: acr.properties.loginServer
          identity: uami.id
        }
      ]
      secrets: [
        { name: 'database-url', keyVaultUrl: kvDatabaseUrl.properties.secretUri, identity: uami.id }
        { name: 'fernet-secret-key', keyVaultUrl: kvFernetKey.properties.secretUri, identity: uami.id }
        { name: 'ingest-secret-key', keyVaultUrl: kvIngestKey.properties.secretUri, identity: uami.id }
        { name: 'task-token-secret', keyVaultUrl: kvTaskTokenSecret.properties.secretUri, identity: uami.id }
      ]
    }
    template: {
      scale: {
        minReplicas: 0
        maxReplicas: 3
        rules: [
          {
            name: 'http-concurrency'
            http: {
              metadata: {
                concurrentRequests: '20'
              }
            }
          }
        ]
      }
      containers: [
        {
          name: 'workbench'
          image: '${acr.properties.loginServer}/${workbenchAppName}:${imageTag}'
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: concat(commonStorageEnv, [
            { name: 'PORT', value: '8080' }
            { name: 'TASK_EXECUTION_MODE', value: 'queue' }
            { name: 'TASK_QUEUE_PROVIDER', value: 'azure' }
            { name: 'DATABASE_URL', secretRef: 'database-url' }
            { name: 'TASK_DATABASE_URL', secretRef: 'database-url' }
            { name: 'FERNET_SECRET_KEY', secretRef: 'fernet-secret-key' }
            { name: 'INGEST_SECRET_KEY', secretRef: 'ingest-secret-key' }
            { name: 'TASK_TOKEN_SECRET', secretRef: 'task-token-secret' }
            { name: 'CORS_ALLOW_ORIGINS', value: effectiveCors }
            { name: 'ADMIN_REPORT_MODE', value: adminReportMode }
            { name: 'ADMIN_API_URL', value: '' }
            { name: 'ROUTER01_MEDIA_BASE_URL', value: 'https://${workbenchAppName}.${acaEnv.properties.defaultDomain}' }
            { name: 'WORKBENCH_PUBLIC_URL', value: 'https://${workbenchAppName}.${acaEnv.properties.defaultDomain}' }
            { name: 'DECART_REALTIME_ORIGIN', value: 'https://${workbenchAppName}.${acaEnv.properties.defaultDomain}' }
            { name: 'XMAX_REALTIME_ORIGIN', value: 'https://${workbenchAppName}.${acaEnv.properties.defaultDomain}' }
            { name: 'REACTOR_REALTIME_ORIGIN', value: 'https://${workbenchAppName}.${acaEnv.properties.defaultDomain}' }
            { name: 'VITE_RECOMMEND_APP_URL', value: 'https://${mainAppName}.${acaEnv.properties.defaultDomain}' }
          ])
          probes: [
            {
              type: 'Startup'
              httpGet: { path: '/health', port: 8080 }
              initialDelaySeconds: 5
              periodSeconds: 5
              failureThreshold: 12
            }
            {
              type: 'Readiness'
              httpGet: { path: '/health', port: 8080 }
              periodSeconds: 10
            }
          ]
        }
      ]
    }
  }
  dependsOn: [acrPullRole, storageBlobRole, storageQueueRole, kvSecretsRole]
}

// 3. tryon-admin (Scale-to-zero Admin portal & backend)
resource adminApp 'Microsoft.App/containerApps@2024-03-01' = if (deployWorkloads) {
  name: adminAppName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${uami.id}': {} }
  }
  properties: {
    managedEnvironmentId: acaEnv.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8080
        transport: 'http'
      }
      registries: [
        {
          server: acr.properties.loginServer
          identity: uami.id
        }
      ]
      secrets: concat([
        { name: 'database-url', keyVaultUrl: kvDatabaseUrl.properties.secretUri, identity: uami.id }
        { name: 'fernet-secret-key', keyVaultUrl: kvFernetKey.properties.secretUri, identity: uami.id }
        { name: 'jwt-secret-key', keyVaultUrl: kvJwtKey.properties.secretUri, identity: uami.id }
        { name: 'ingest-secret-key', keyVaultUrl: kvIngestKey.properties.secretUri, identity: uami.id }
        { name: 'admin-init-password', keyVaultUrl: kvAdminInitPassword.properties.secretUri, identity: uami.id }
      ], empty(adminRecoveryKey) ? [] : [
        { name: 'admin-recovery-key', keyVaultUrl: 'https://${kvName}${environment().suffixes.keyvaultDns}/secrets/admin-recovery-key', identity: uami.id }
      ])
    }
    template: {
      scale: {
        minReplicas: 0
        maxReplicas: 1
        rules: [
          {
            name: 'http-concurrency'
            http: {
              metadata: {
                concurrentRequests: '10'
              }
            }
          }
        ]
      }
      containers: [
        {
          name: 'admin'
          image: '${acr.properties.loginServer}/${adminAppName}:${empty(adminImageTag) ? imageTag : adminImageTag}'
          resources: {
            cpu: json(adminCpu)
            memory: adminMemory
          }
          env: concat(commonStorageEnv, [
            { name: 'PORT', value: '8080' }
            { name: 'DATABASE_URL', secretRef: 'database-url' }
            { name: 'FERNET_SECRET_KEY', secretRef: 'fernet-secret-key' }
            { name: 'JWT_SECRET_KEY', secretRef: 'jwt-secret-key' }
            { name: 'INGEST_SECRET_KEY', secretRef: 'ingest-secret-key' }
            { name: 'ADMIN_INIT_USERNAME', value: adminInitUsername }
            { name: 'ADMIN_INIT_PASSWORD', secretRef: 'admin-init-password' }
            { name: 'RUN_STARTUP_DB_INIT', value: 'false' }
            { name: 'CORS_ALLOW_ORIGINS', value: effectiveCors }
            { name: 'MAIN_SITE_URL', value: 'https://${mainAppName}.${acaEnv.properties.defaultDomain}' }
            { name: 'TRYON_WORKBENCH_URL', value: 'https://${workbenchAppName}.${acaEnv.properties.defaultDomain}' }
          ], empty(adminRecoveryKey) ? [] : [
            { name: 'ADMIN_RECOVERY_KEY', secretRef: 'admin-recovery-key' }
          ])
          probes: [
            {
              type: 'Startup'
              httpGet: { path: '/health', port: 8080 }
              initialDelaySeconds: 5
              periodSeconds: 5
              failureThreshold: 12
            }
            {
              type: 'Readiness'
              httpGet: { path: '/health', port: 8080 }
              periodSeconds: 10
            }
          ]
        }
      ]
    }
  }
  dependsOn: [acrPullRole, storageBlobRole, kvSecretsRole, kvAdminRecoveryKey]
}

// 4. tryon-db-init (Manual ACA Job for idempotent schema migration & 4721 product seed)
resource dbInitJob 'Microsoft.App/jobs@2024-03-01' = if (deployWorkloads) {
  name: dbInitJobName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${uami.id}': {} }
  }
  properties: {
    environmentId: acaEnv.id
    configuration: {
      triggerType: 'Manual'
      replicaTimeout: 1800
      replicaRetryLimit: 1
      manualTriggerConfig: {
        parallelism: 1
        replicaCompletionCount: 1
      }
      registries: [
        {
          server: acr.properties.loginServer
          identity: uami.id
        }
      ]
      secrets: [
        { name: 'database-url', keyVaultUrl: kvDatabaseUrl.properties.secretUri, identity: uami.id }
        { name: 'fernet-secret-key', keyVaultUrl: kvFernetKey.properties.secretUri, identity: uami.id }
        { name: 'jwt-secret-key', keyVaultUrl: kvJwtKey.properties.secretUri, identity: uami.id }
        { name: 'ingest-secret-key', keyVaultUrl: kvIngestKey.properties.secretUri, identity: uami.id }
        { name: 'admin-init-password', keyVaultUrl: kvAdminInitPassword.properties.secretUri, identity: uami.id }
      ]
    }
    template: {
      containers: [
        {
          name: 'db-init'
          image: '${acr.properties.loginServer}/${adminAppName}:${imageTag}'
          command: ['python', '-m', 'app.db_init_job']
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: concat(commonStorageEnv, [
            { name: 'DATABASE_URL', secretRef: 'database-url' }
            { name: 'FERNET_SECRET_KEY', secretRef: 'fernet-secret-key' }
            { name: 'JWT_SECRET_KEY', secretRef: 'jwt-secret-key' }
            { name: 'INGEST_SECRET_KEY', secretRef: 'ingest-secret-key' }
            { name: 'ADMIN_INIT_USERNAME', value: adminInitUsername }
            { name: 'ADMIN_INIT_PASSWORD', secretRef: 'admin-init-password' }
          ])
        }
      ]
    }
  }
  dependsOn: [acrPullRole, kvSecretsRole, pgDb, pgFirewallAzure]
}

// 5. tryon-worker (Event-driven ACA Job processing Storage Queue tryon-tasks; scales 0 -> N -> 0)
resource workerJob 'Microsoft.App/jobs@2025-01-01' = if (deployWorkloads) {
  name: workerJobName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${uami.id}': {} }
  }
  properties: {
    environmentId: acaEnv.id
    configuration: {
      triggerType: 'Event'
      replicaTimeout: 900
      replicaRetryLimit: 1
      eventTriggerConfig: {
        parallelism: 1
        replicaCompletionCount: 1
        scale: {
          minExecutions: 0
          maxExecutions: 3
          pollingInterval: 15
          rules: [
            {
              name: 'azure-queue-tryon-tasks'
              type: 'azure-queue'
              identity: uami.id
              metadata: {
                accountName: storageAccount.name
                queueName: queueName
                queueLength: '1'
              }
            }
          ]
        }
      }
      registries: [
        {
          server: acr.properties.loginServer
          identity: uami.id
        }
      ]
      secrets: [
        { name: 'database-url', keyVaultUrl: kvDatabaseUrl.properties.secretUri, identity: uami.id }
        { name: 'fernet-secret-key', keyVaultUrl: kvFernetKey.properties.secretUri, identity: uami.id }
        { name: 'ingest-secret-key', keyVaultUrl: kvIngestKey.properties.secretUri, identity: uami.id }
        { name: 'task-token-secret', keyVaultUrl: kvTaskTokenSecret.properties.secretUri, identity: uami.id }
      ]
    }
    template: {
      containers: [
        {
          name: 'worker'
          image: '${acr.properties.loginServer}/${workerJobName}:${imageTag}'
          command: ['python', '-m', 'app.queue_worker']
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: concat(commonStorageEnv, [
            { name: 'TASK_EXECUTION_MODE', value: 'queue' }
            { name: 'TASK_QUEUE_PROVIDER', value: 'azure' }
            { name: 'DATABASE_URL', secretRef: 'database-url' }
            { name: 'TASK_DATABASE_URL', secretRef: 'database-url' }
            { name: 'FERNET_SECRET_KEY', secretRef: 'fernet-secret-key' }
            { name: 'INGEST_SECRET_KEY', secretRef: 'ingest-secret-key' }
            { name: 'TASK_TOKEN_SECRET', secretRef: 'task-token-secret' }
            { name: 'ADMIN_REPORT_MODE', value: adminReportMode }
            { name: 'ADMIN_API_URL', value: '' }
            { name: 'WORKER_LEASE_SECONDS', value: '180' }
            { name: 'WORKER_RENEW_INTERVAL_SECONDS', value: '60' }
            { name: 'WORKER_VISIBILITY_TIMEOUT_SECONDS', value: '240' }
          ])
        }
      ]
    }
  }
  dependsOn: [acrPullRole, storageBlobRole, storageQueueRole, kvSecretsRole, taskQueue]
}

output acaDefaultDomain string = acaEnv.properties.defaultDomain
output acrLoginServer string = acr.properties.loginServer
output storageAccountName string = storageAccount.name
output postgresServerFqdn string = '${pgServer.name}.postgres.database.azure.com'
output mainAppUrl string = 'https://${mainAppName}.${acaEnv.properties.defaultDomain}'
output workbenchAppUrl string = 'https://${workbenchAppName}.${acaEnv.properties.defaultDomain}'
output adminAppUrl string = 'https://${adminAppName}.${acaEnv.properties.defaultDomain}'
output dbInitJobName string = dbInitJobName
output workerJobName string = workerJobName
