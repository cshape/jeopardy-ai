const fs = require('fs');
const path = require('path');

// Utility function to wait for a specific amount of time
async function wait(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

module.exports = {
  wait
}; 