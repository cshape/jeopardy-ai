import React from 'react';
import { useGame } from './contexts/GameContext';
import GameBoard from './components/GameBoard';
import AdminControls from './components/Admin/AdminControls';
import QuestionModal from './components/Modals/QuestionModal';
import PlayerRegistrationModal from './components/Modals/PlayerRegistrationModal';
import ScoreBoard from './components/ScoreBoard/ScoreBoard';
import ChatWindow from './components/Chat/ChatWindow';
import './styles/layout.css';

function App() {
  const { state } = useGame();
  const { registered, adminMode, board, gameReady } = state;

  // Admin mode should bypass player registration
  if (!registered && !adminMode) {
    return <PlayerRegistrationModal />;
  }

  return (
    <div className="app">
      {/* {adminMode && (
        <div className="admin-bar">
          <AdminControls />
          <div className="admin-indicator">Admin Mode Active</div>
        </div>
      )} */}
      
      <div className="main-content">
        <div className="board-container">
          {board && (adminMode || gameReady || state.boardGenerating) ? (
            <GameBoard />
          ) : (
            <div className="waiting-screen">
              <h2>Waiting for Players</h2>
              <p>Please wait while players join...</p>
              {Object.keys(state.players).length > 0 && (
                <div className="current-players">
                  <h3>Current Players:</h3>
                  <ul>
                    {Object.keys(state.players).map(name => (
                      <li key={name}>{name}</li>
                    ))}
                  </ul>
                  <p>Need {3 - Object.keys(state.players).length} more player(s) to start</p>
                </div>
              )}
            </div>
          )}
          {/* Modal will overlay the board when active */}
          <QuestionModal />
        </div>
        
        <div className="score-container">
          <ScoreBoard />
          <ChatWindow />
        </div>
      </div>
    </div>
  );
}

export default App; 