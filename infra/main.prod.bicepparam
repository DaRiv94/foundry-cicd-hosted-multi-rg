using 'main.bicep'

param env = 'prod'
// Prod gets more capacity. Everything else is identical to dev and test.
param chatCapacity = 20
