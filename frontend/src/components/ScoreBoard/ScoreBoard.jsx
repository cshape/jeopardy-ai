import React from 'react';
import { useGame } from '../../contexts/GameContext';
import './ScoreBoard.css';

export default function ScoreBoard() {
  const { state } = useGame();
  const { players } = state;

  return (
    <div className="score-board">
      <div className="player-scores">
        {Object.entries(players).map(([name, data]) => (
          <div key={name} className="player-score">
            <span className="player-name">{name}</span>
            <span className="score">${data.score}</span>
          </div>
        ))}
      </div>
    </div>
  );
} 