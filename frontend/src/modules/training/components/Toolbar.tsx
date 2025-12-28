import React from 'react'
import type { AnnotationBox } from '../types'
import { CircleDashed, Cookie, CloudFog, Activity, Save } from 'lucide-react'

interface ToolbarProps {
  selectedTool: AnnotationBox['label']
  setTool: (tool: AnnotationBox['label']) => void
  onSave: () => void
}

const TOOLS = [
  { id: 'pothole', label: 'Pothole', shortcut: 'P', icon: <CircleDashed size={24} /> },
  { id: 'patch', label: 'Patch', shortcut: 'A', icon: <Cookie size={24} /> }, // Cookie looks a bit like a patch/blob
  { id: 'shadow', label: 'Shadow', shortcut: 'S', icon: <CloudFog size={24} /> },
  { id: 'cracks', label: 'Cracks', shortcut: 'C', icon: <Activity size={24} /> },
]

const Toolbar: React.FC<ToolbarProps> = ({ selectedTool, setTool, onSave }) => {
  return (
    <div
      style={{
        width: '60px',
        background: '#1e1e1e', // Darker cleaner background
        borderRight: '1px solid #333',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        paddingTop: '15px',
        gap: '12px',
        zIndex: 50, // Ensure it stays on top
      }}>
      {TOOLS.map(tool => (
        <button
          key={tool.id}
          onClick={() => setTool(tool.id as AnnotationBox['label'])}
          title={`${tool.label} (${tool.shortcut})`}
          style={{
            width: '40px',
            height: '40px',
            background: selectedTool === tool.id ? '#4a4a4a' : 'transparent',
            color: selectedTool === tool.id ? '#fff' : '#aaa',
            border: 'none',
            borderRadius: '4px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            transition: 'all 0.2s',
          }}>
          {tool.icon}
        </button>
      ))}

      <div
        style={{
          marginTop: 'auto',
          marginBottom: '20px',
          width: '100%',
          display: 'flex',
          justifyContent: 'center',
        }}>
        <button
          onClick={onSave}
          title="Save (Enter)"
          style={{
            width: '40px',
            height: '40px',
            background: '#2ecc71',
            color: 'white',
            border: 'none',
            borderRadius: '6px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 4px 6px rgba(0,0,0,0.3)',
          }}>
          <Save size={24} />
        </button>
      </div>
    </div>
  )
}

export default Toolbar
