import React from 'react';
import { useGame } from '../../contexts/GameContext';

export default function QuestionCell({ question, categoryName, isAdmin, isPlaceholder }) {
  const { sendMessage } = useGame();

  const handleClick = () => {
    if (!isAdmin || question.used || isPlaceholder) return;

    // If it's a daily double, use a different message
    if (question.daily_double) {
      sendMessage('com.sc2ctl.jeopardy.daily_double', {
        category: categoryName,
        value: question.value
      });
    } else {
      sendMessage('com.sc2ctl.jeopardy.question_display', {
        category: categoryName,
        value: question.value
      });
    }
  };

  return (
    <div 
      className={`question ${question.used ? 'used' : ''} ${isPlaceholder ? 'placeholder' : ''}`}
      onClick={handleClick}
    >
      ${question.value}
    </div>
  );
} 