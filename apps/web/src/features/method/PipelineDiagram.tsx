import React from 'react';
import { METHOD_COPY as C } from './copy';
import styles from './PipelineDiagram.module.css';

const NODES = C.pipeline.nodes;
const ICON_STROKE = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.6, strokeLinecap: 'round', strokeLinejoin: 'round' } as const;

/** Tiny glyph per stage, drawn in a 24x24 box at (0,0). */
function Glyph({ i }: { i: number }) {
  switch (i) {
    case 0: return <g {...ICON_STROKE}><ellipse cx="12" cy="6" rx="8" ry="3" /><path d="M4 6v6c0 1.7 3.6 3 8 3s8-1.300 8-3V6M4 12v6c0 1.700 3.600 3 8 3s8-1.300 8-3v-6" /></g>;
    case 1: return <g {...ICON_STROKE}><circle cx="6" cy="7" r="2.500" /><circle cx="18" cy="7" r="2.500" /><circle cx="6" cy="17" r="2.500" /><circle cx="18" cy="17" r="2.500" /></g>;
    case 2: return <g {...ICON_STROKE}><path d="M3 17l5-6 4 3 4-7 5 5" /><path d="M3 20h18" strokeDasharray="2 3" /></g>;
    case 3: return <g {...ICON_STROKE}><path d="M3 18l6-6 4 3 8-9" /><path d="M21 6v5M21 6h-5" /></g>;
    case 4: return <g {...ICON_STROKE}><path d="M3 20V12M8 20V8M13 20V14M18 20V4" /><path d="M2 20h20" /></g>;
    case 5: return <g {...ICON_STROKE}><rect x="4" y="3" width="16" height="18" rx="2" /><path d="M8 8h8M8 12h8M8 16h5" /></g>;
    default: return <g {...ICON_STROKE}><circle cx="12" cy="12" r="9" /><path d="M8 12.500l3 3 5-6" /></g>;
  }
}

function Node({ i, x, y, w, h }: { i: number; x: number; y: number; w: number; h: number }) {
  const n = NODES[i];
  const last = i === NODES.length - 1;
  return (
    <g transform={`translate(${x} ${y})`} className={last ? styles.nodeEnd : styles.node}>
      <rect width={w} height={h} rx="12" />
      <g transform={`translate(${w / 2 - 12} 12)`}><Glyph i={i} /></g>
      <text x={w / 2} y={52} textAnchor="middle" className={styles.t1}>{n.label}</text>
      <text x={w / 2} y={68} textAnchor="middle" className={styles.t2}>{n.sub}</text>
    </g>
  );
}

export function PipelineDiagram() {
  const w = 96, h = 80, gap = 22;
  const wideW = NODES.length * w + (NODES.length - 1) * gap;
  const tallH = NODES.length * h + (NODES.length - 1) * 28;
  return (
    <figure className={styles.fig}>
      <svg className={styles.wide} viewBox={`0 0 ${wideW} ${h}`} role="img" aria-label={C.pipeline.alt}>
        {NODES.map((_, i) => (
          <React.Fragment key={i}>
            {i > 0 && <path d={`M${i * (w + gap) - gap + 3} ${h / 2}h${gap - 8}m-4 -4l4 4l-4 4`} className={styles.arrow} />}
            <Node i={i} x={i * (w + gap)} y={0} w={w} h={h} />
          </React.Fragment>
        ))}
      </svg>
      <svg className={styles.tall} viewBox={`0 0 220 ${tallH}`} role="img" aria-label={C.pipeline.alt}>
        {NODES.map((_, i) => (
          <React.Fragment key={i}>
            {i > 0 && <path d={`M110 ${i * (h + 28) - 24}v16m-4 -4l4 4l4 -4`} className={styles.arrow} />}
            <Node i={i} x={10} y={i * (h + 28)} w={200} h={h} />
          </React.Fragment>
        ))}
      </svg>
      <figcaption className={styles.cap}>{C.pipeline.caption}</figcaption>
    </figure>
  );
}
