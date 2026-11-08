import { AnimatePresence, motion } from "framer-motion";
import { color, map } from "../../theme/tokens";
import type { MapData, Point } from "../../shared/api/types";

const M_PER_DEG = 111_320;

/** The development area as merged places. Duplicates and wrong merges, found against the world, are ringed. */
export function ConflationMap({ data, mode }: { data: MapData; mode: "full" | "naive" }) {
  const [lon0, lat0, split, lat1] = data.box;
  const k = Math.cos((((lat0 + lat1) / 2) * Math.PI) / 180);
  const spanX = (data.lon_max - lon0) * k;
  const W = map.width;
  const H = (W * (lat1 - lat0)) / spanX;
  const x = (lon: number) => ((lon - lon0) * k * W) / spanX;
  const y = (lat: number) => ((lat1 - lat) * H) / (lat1 - lat0);
  const pts: Point[] = data[mode];
  const marked = pts.filter((p) => p[2] !== 0);
  const pxPerM = W / ((data.lon_max - lon0) * k * M_PER_DEG);
  const bar = map.scaleM * pxPerM;
  return (
    <svg className="map" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${pts.length} places in the development area, ${marked.length} of them duplicates or wrong merges`}>
      <defs>
        <pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <line x1="0" y1="0" x2="0" y2="6" stroke={color.hatch} strokeWidth="2" />
        </pattern>
      </defs>
      <rect x={x(split)} y={0} width={W - x(split)} height={H} fill="url(#hatch)" />
      <line x1={x(split)} x2={x(split)} y1={0} y2={H} stroke={color.rule} />
      <text className="map__area" x={x(split) + 10} y={22}>
        Held-out area
      </text>
      <text className="map__area map__area--sub" x={x(split) + 10} y={38}>
        scored once, at the end
      </text>
      {pts.map((p, i) => (
        <circle key={i} cx={x(p[0])} cy={y(p[1])} r={map.point} fill={p[3] === 2 ? color.ink : color.faint} opacity={p[3] === 2 ? 0.75 : 0.6} />
      ))}
      <AnimatePresence mode="wait">
        <motion.g key={mode} initial={{ opacity: 1 }} animate={{ opacity: 1 }} exit={{ opacity: 0, transition: { duration: 0.12 } }}>
          {marked.map((p, i) =>
            p[2] === 1 ? (
              <motion.circle
                key={i}
                cx={x(p[0])}
                cy={y(p[1])}
                r={map.ring}
                fill="none"
                stroke={color.signal}
                strokeWidth={1.4}
                initial={{ opacity: 0, scale: 2.4 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ duration: map.ringIn, delay: i * map.ringStagger }}
                style={{ transformBox: "fill-box", transformOrigin: "center" }}
              />
            ) : (
              <motion.path
                key={i}
                d={`M${x(p[0]) - map.cross},${y(p[1]) - map.cross}L${x(p[0]) + map.cross},${y(p[1]) + map.cross}M${x(p[0]) - map.cross},${y(p[1]) + map.cross}L${x(p[0]) + map.cross},${y(p[1]) - map.cross}`}
                stroke={color.signal}
                strokeWidth={1.8}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: map.ringIn, delay: i * map.ringStagger }}
              />
            ),
          )}
        </motion.g>
      </AnimatePresence>
      <g transform={`translate(${16}, ${H - 18})`} className="map__scale">
        <rect width={bar / 2} height={4} fill={color.ink} />
        <rect x={bar / 2} width={bar / 2} height={4} fill={color.sheet} stroke={color.ink} strokeWidth={0.8} />
        <text x={0} y={-6} textAnchor="middle">
          0
        </text>
        <text x={bar} y={-6} textAnchor="middle">
          {map.scaleM / 1000} km
        </text>
      </g>
    </svg>
  );
}

export function MapKey() {
  return (
    <dl className="key" aria-label="Map key">
      <div className="key__row">
        <dt>
          <svg width="14" height="14" aria-hidden="true">
            <circle cx="7" cy="7" r="2.4" fill={color.ink} opacity="0.75" />
          </svg>
        </dt>
        <dd>A place both sources list</dd>
      </div>
      <div className="key__row">
        <dt>
          <svg width="14" height="14" aria-hidden="true">
            <circle cx="7" cy="7" r="2.4" fill={color.faint} />
          </svg>
        </dt>
        <dd>A place from one source</dd>
      </div>
      <div className="key__row">
        <dt>
          <svg width="14" height="14" aria-hidden="true">
            <circle cx="7" cy="7" r="5" fill="none" stroke={color.signal} strokeWidth="1.4" />
          </svg>
        </dt>
        <dd>A place listed more than once, every copy ringed</dd>
      </div>
      <div className="key__row">
        <dt>
          <svg width="14" height="14" aria-hidden="true">
            <path d="M3,3L11,11M3,11L11,3" stroke={color.signal} strokeWidth="1.8" />
          </svg>
        </dt>
        <dd>Two different places merged into one</dd>
      </div>
    </dl>
  );
}
