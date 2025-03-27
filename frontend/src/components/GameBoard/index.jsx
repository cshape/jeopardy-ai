import React from 'react';
import { useGame } from '../../contexts/GameContext';
import CategoryColumn from './CategoryColumn';
import './GameBoard.css';

export default function GameBoard() {
  const { state } = useGame();
  
  if (!state.board) {
    return <div className="loading">Loading game board...</div>;
  }

  // Add safety check for categories
  if (!Array.isArray(state.board?.categories)) {
    console.log('Current board state:', state.board);
    return <div className="loading">Waiting for categories...</div>;
  }

  return (
    <div className={`jeopardy-board ${state.boardGenerating ? 'generating' : ''}`}>
      {state.board.categories.map((category, index) => (
        <CategoryColumn 
          key={index}
          category={category}
          isAdmin={state.adminMode}
          isPlaceholder={state.boardGenerating && !state.revealedCategories.has(index)}
          isRevealing={state.boardGenerating && state.revealedCategories.has(index)}
        />
      ))}
    </div>
  );
} 