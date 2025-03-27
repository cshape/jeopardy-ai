const util = require('util');
const { exec } = require('child_process');
const execPromise = util.promisify(exec);

async function setupTestEnvironment() {
  try {
    // Start the server
    console.log('Starting test environment...');
    
    // Start the backend server (this will be handled by Jest's setupFiles)
    return true;
  } catch (error) {
    console.error('Error setting up test environment:', error);
    throw error;
  }
}

module.exports = { setupTestEnvironment }; 