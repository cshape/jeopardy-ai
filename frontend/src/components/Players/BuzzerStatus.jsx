import React from 'react';
import { useGame } from '../../contexts/GameContext';

export default function BuzzerStatus() {
  const { state } = useGame();
  
  return (
    <div className={`buzzer-status ${state.buzzerActive ? 'active' : ''}`}>
      {state.buzzerActive ? 'Buzzer Active!' : 'Wait...'}
    </div>
  );
} 