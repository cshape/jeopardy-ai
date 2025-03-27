const puppeteer = require('puppeteer');
const { setupTestEnvironment } = require('./setup');
const { wait } = require('./helpers');
const util = require('util');
const { exec } = require('child_process');
const execPromise = util.promisify(exec);

jest.setTimeout(60000); // Increase the timeout to 60 seconds for the entire test suite

describe('Jeopardy App E2E Tests', () => {
  // Use separate browser instances for admin and players
  let adminBrowser;
  let playerBrowsers = [];
  let adminPage;
  let playerPages = [];
  
  beforeAll(async () => {
    try {
      await setupTestEnvironment();
    } catch (error) {
      console.error('Error in beforeAll:', error);
      throw error;
    }
  });

  afterAll(async () => {
    // Close all browser instances
    if (adminBrowser) {
      await adminBrowser.close();
    }
    
    for (const browser of playerBrowsers) {
      await browser.close();
    }
    
    try {
      // Clean up any remaining processes
      await execPromise('pkill -f "python -m app.main"');
      console.log('Killed server processes');
    } catch (error) {
      console.log('No server processes to kill');
    }
  });
  
  // beforeEach test setup
  beforeEach(async () => {
    // No server restart needed
  });

  test('Admin can select a board and players can join the game', async () => {
    // Launch admin browser
    adminBrowser = await puppeteer.launch({
      headless: 'new', // Use headless mode
      args: ['--window-size=1280,800']
    });
    
    // 1. Admin opens the app and selects a board
    adminPage = await adminBrowser.newPage();
    await adminPage.setViewport({ width: 1280, height: 800 });
    
    console.log('Admin navigating to app with admin mode...');
    await adminPage.goto('http://localhost:5173/?admin=true', { waitUntil: 'networkidle0' });
    
    // Wait for board selector to appear
    await adminPage.waitForSelector('.board-selector');
    
    // Select the first board
    const boardOptions = await adminPage.$$('.board-option');
    if (boardOptions.length > 0) {
      console.log('Admin selecting a board...');
      await boardOptions[0].click();
      
      // Wait for the board to load
      await adminPage.waitForSelector('.jeopardy-board', { timeout: 5000 });
      
      // Verify that categories are displayed
      const categories = await adminPage.$$('.category-title');
      expect(categories.length).toBeGreaterThan(0);
      console.log(`Admin sees ${categories.length} categories`);
    } else {
      throw new Error('No board options found');
    }
    
    // 2. Players join one by one
    console.log('Creating player browsers...');
    
    // Create 3 player browsers and pages
    for (let i = 0; i < 3; i++) {
      const playerBrowser = await puppeteer.launch({
        headless: 'new', // Use headless mode
        args: ['--window-size=1280,800']
      });
      playerBrowsers.push(playerBrowser);
      
      const playerPage = await playerBrowser.newPage();
      await playerPage.setViewport({ width: 1280, height: 800 });
      playerPages.push(playerPage);
    }
    
    // First player joins
    console.log('Player 1 joining...');
    await playerPages[0].goto('http://localhost:5173', { waitUntil: 'networkidle0' });
    
    // Enter player 1 name and submit
    await playerPages[0].type('input[type="text"]', 'Player 1');
    await playerPages[0].click('button[type="submit"]');
    
    // Verify player 1 entered waiting state
    await playerPages[0].waitForSelector('.waiting-screen', { timeout: 5000 });
    
    // Second player joins
    console.log('Player 2 joining...');
    await playerPages[1].goto('http://localhost:5173', { waitUntil: 'networkidle0' });
    await playerPages[1].type('input[type="text"]', 'Player 2');
    await playerPages[1].click('button[type="submit"]');
    
    // Verify player 2 entered waiting state
    await playerPages[1].waitForSelector('.waiting-screen', { timeout: 5000 });
    
    // Verify that both players see each other in the waiting room
    const player1Names = await playerPages[0].$$eval('.current-players li', elements => 
      elements.map(el => el.textContent)
    );
    
    expect(player1Names).toContain('Player 1');
    expect(player1Names).toContain('Player 2');
    
    // Third player joins (this should start the game)
    console.log('Player 3 joining...');
    await playerPages[2].goto('http://localhost:5173', { waitUntil: 'networkidle0' });
    await playerPages[2].type('input[type="text"]', 'Player 3');
    await playerPages[2].click('button[type="submit"]');
    
    // Wait for the game to start for all players
    console.log('Waiting for game board to appear for all players...');
    
    // Wait for all players to see the game board
    const boardPromises = playerPages.map(page =>
      page.waitForSelector('.jeopardy-board', { timeout: 10000 })
    );
    await Promise.all(boardPromises);
    
    // Verify that all players see the game board
    for (let i = 0; i < playerPages.length; i++) {
      const categories = await playerPages[i].$$('.category-title');
      expect(categories.length).toBeGreaterThan(0);
      console.log(`Player ${i+1} sees ${categories.length} categories`);
    }
    
    // Verify that all players are shown in the scoreboard
    for (let i = 0; i < playerPages.length; i++) {
      const playerScores = await playerPages[i].$$('.player-score');
      expect(playerScores.length).toBe(3);
      
      const playerNames = await playerPages[i].$$eval('.player-name', elements => 
        elements.map(el => el.textContent)
      );
      
      expect(playerNames).toContain('Player 1');
      expect(playerNames).toContain('Player 2');
      expect(playerNames).toContain('Player 3');
    }
    
    console.log('Test completed successfully!');
  }, 60000);

  test('Admin shows question, players see it, and admin dismisses it', async () => {
    // Assume adminPage and playerPages are already set up from previous test
    
    // Admin selects a question
    console.log('Admin selecting a question...');
    const questionCells = await adminPage.$$('.question');
    await questionCells[0].click();

    // Wait for question modal to appear
    await adminPage.waitForSelector('.modal-content', { timeout: 5000 });
    
    // Verify all players see the question
    for (let i = 0; i < playerPages.length; i++) {
      await playerPages[i].waitForSelector('.modal-content', { timeout: 5000 });
    }

    // Admin dismisses the question
    console.log('Admin dismissing question...');
    await adminPage.click('.dismiss');

    // Verify admin no longer sees the modal
    await adminPage.waitForSelector('.modal-content', { hidden: true, timeout: 5000 });
    
    // Verify all players no longer see the modal
    for (let i = 0; i < playerPages.length; i++) {
      await playerPages[i].waitForSelector('.modal-content', { hidden: true, timeout: 5000 });
    }
  }, 60000);

  test('Player buzzes in, admin marks answer as incorrect', async () => {
    // Assume adminPage and playerPages are already set up from previous test
    
    // Admin selects a question
    console.log('Admin selecting a question...');
    const questionCells2 = await adminPage.$$('.question');
    await questionCells2[1].click();

    // Wait for question modal to appear
    await adminPage.waitForSelector('.modal-content', { timeout: 5000 });
    
    // Player 1 buzzes in
    console.log('Player 1 buzzing in...');
    await playerPages[0].click('.player-buzzer');
    
    // Wait for admin to see the buzz (this is more reliable than a fixed wait)
    await adminPage.waitForSelector('.admin-controls p', { timeout: 5000 });
    
    // Verify admin sees the buzz
    const buzzedInText = await adminPage.$eval('.admin-controls p', el => el.textContent);
    expect(buzzedInText).toContain('Player 1');
    
    // Admin marks answer as incorrect
    console.log('Admin marking answer as incorrect...');
    await adminPage.click('.incorrect');
    await adminPage.waitForSelector('.modal-content', { hidden: true, timeout: 5000 });

    // Verify player sees the result
    await playerPages[0].waitForSelector('.modal-content', { hidden: true, timeout: 5000 });

    // Verify Player 1's score has decreased
    const player1Score = await playerPages[0].evaluate(() => {
      // Find the player-score element that contains "Player 1"
      const playerScoreElements = document.querySelectorAll('.player-score');
      for (const element of playerScoreElements) {
        if (element.querySelector('.player-name').textContent.includes('Player 1')) {
          return parseInt(element.querySelector('.score').textContent.replace('$', ''));
        }
      }
      return null; // Player 1 not found
    });
    
    expect(player1Score).not.toBeNull();
    expect(player1Score).toBeLessThan(0);
  }, 60000);

  test('Player buzzes in, admin marks answer as correct', async () => {
    // Assume adminPage and playerPages are already set up from previous test

    // Admin selects a question
    console.log('Admin selecting a question...');
    const questionCells3 = await adminPage.$$('.question');
    await questionCells3[2].click();

    // Wait for question modal to appear
    await adminPage.waitForSelector('.modal-content', { timeout: 5000 });

    // Player 2 buzzes in
    console.log('Player 2 buzzing in...');
    await playerPages[1].click('.player-buzzer');
    
    // Wait for admin to see the buzz (this is more reliable than a fixed wait)
    await adminPage.waitForSelector('.admin-controls p', { timeout: 5000 });

    // Verify admin sees the buzz
    const buzzedInText2 = await adminPage.$eval('.admin-controls p', el => el.textContent);
    expect(buzzedInText2).toContain('Player 2');
    
    // Admin marks answer as correct
    console.log('Admin marking answer as correct...');
    await adminPage.click('.correct');
    await adminPage.waitForSelector('.modal-content', { hidden: true, timeout: 5000 });

    // Verify player sees the result
    await playerPages[1].waitForSelector('.modal-content', { hidden: true, timeout: 5000 });

    // Verify Player 2's score has increased
    const player2Score = await playerPages[1].evaluate(() => {
      // Find the player-score element that contains "Player 2"
      const playerScoreElements = document.querySelectorAll('.player-score');
      for (const element of playerScoreElements) {
        if (element.querySelector('.player-name').textContent.includes('Player 2')) {
          return parseInt(element.querySelector('.score').textContent.replace('$', ''));
        }
      }
      return null; // Player 2 not found
    });
    
    expect(player2Score).not.toBeNull();
    expect(player2Score).toBeGreaterThan(0);
  }, 60000);

  test('Player encounters a daily double, bets and answers correctly', async () => {
    // Assume adminPage and playerPages are already set up from previous test
    
    // Simplest approach: just try ALL questions one by one
    console.log('Admin searching for a daily double question...');
    
    // Get all questions
    const allQuestions = await adminPage.$$('.question');
    console.log(`Found ${allQuestions.length} total questions`);
    
    let foundDailyDouble = false;
    
    // Try each question until we find a daily double
    for (let i = 0; i < allQuestions.length && !foundDailyDouble; i++) {
      // Skip questions that have already been clicked (they'll have a different appearance)
      const isClicked = await adminPage.evaluate(el => {
        return el.classList.contains('clicked') || 
               getComputedStyle(el).getPropertyValue('visibility') === 'hidden';
      }, allQuestions[i]);
      
      if (isClicked) {
        console.log(`Skipping question ${i} - already clicked`);
        continue;
      }
      
      console.log(`Trying question at index ${i}...`);
      try {
        // Click the question
        await allQuestions[i].click();
        
        // Wait for modal to appear
        await adminPage.waitForSelector('.modal-content', { timeout: 500 });
        
        // Check if it's a daily double by checking if the select player dropdown exists
        const isDD = await adminPage.evaluate(() => {
          return !!document.querySelector('.modal-content select');
        });
        
        if (isDD) {
          console.log(`Found a daily double at index ${i}!`);
          foundDailyDouble = true;
        } else {
          // Not a daily double, dismiss and try another
          console.log('Not a daily double, dismissing...');
          await adminPage.click('.dismiss');
          await adminPage.waitForSelector('.modal-content', { hidden: true, timeout: 500 });
        }
      } catch (e) {
        console.log(`Error with question ${i}, skipping: ${e.message}`);
        // If there was an error (like a timeout), try to dismiss any modal that might be open
        try {
          await adminPage.click('.dismiss');
        } catch (dismissError) {
          // Ignore errors when trying to dismiss
        }
      }
    }
    
    if (foundDailyDouble) {
      // At this point, we've found a daily double and the modal is open
      
      // Select Player 3 for the daily double
      console.log('Selecting Player 3 for daily double...');
      await adminPage.select('select', 'Player 3');
      
      // Enter wager amount
      console.log('Entering wager of $1000...');
      await adminPage.type('input[type="number"]', '1000');
      
      // Submit the wager
      await adminPage.click('button[type="submit"]');
      
      // Just wait a bit for the UI to update
      // Use page.evaluate to create a timeout since waitForTimeout isn't available
      await adminPage.evaluate(() => new Promise(resolve => setTimeout(resolve, 2000)));
      
      // Mark the answer as correct (the button should be visible after submitting the wager)
      console.log('Admin marking answer as correct...');
      await adminPage.click('.correct');
      
      // Wait for modal to close
      await adminPage.waitForSelector('.modal-content', { hidden: true, timeout: 5000 });
      
      // Wait a bit to make sure scores update
      await adminPage.evaluate(() => new Promise(resolve => setTimeout(resolve, 2000)));
      
      // Verify Player 3's score has increased
      const player3Score = await playerPages[2].evaluate(() => {
        const playerScoreElements = document.querySelectorAll('.player-score');
        for (const element of playerScoreElements) {
          if (element.querySelector('.player-name').textContent.includes('Player 3')) {
            return parseInt(element.querySelector('.score').textContent.replace('$', ''));
          }
        }
        return null;
      });
      
      console.log(`Player 3 score: ${player3Score}`);
      expect(player3Score).not.toBeNull();
      expect(player3Score).toBeGreaterThan(0); // Should have gained points
    } else {
      console.error("Could not find any daily double question");
      throw new Error("Could not find any daily double question");
    }
  }, 60000);
}); 