import React from 'react'

interface TopProgressBarProps {
  isLoading: boolean
}

export const TopProgressBar: React.FC<TopProgressBarProps> = ({ isLoading }) => {
  if (!isLoading) return null

  return (
    <div className="ui-top-progress-container">
      <div className="ui-top-progress-bar" />
      <style>{`
        .ui-top-progress-container {
          position: fixed;
          top: 0;
          left: 0;
          width: 100%;
          height: 3px;
          z-index: 9999;
          pointer-events: none;
        }
        .ui-top-progress-bar {
          width: 100%;
          height: 100%;
          background: linear-gradient(90deg, #3b82f6, #8b5cf6, #ec4899, #3b82f6);
          background-size: 200% 100%;
          animation: ui-shimmer 1.5s infinite linear;
          transform-origin: 0 50%;
        }
        @keyframes ui-shimmer {
          0% { background-position: 100% 0; }
          100% { background-position: -100% 0; }
        }
      `}</style>
    </div>
  )
}
