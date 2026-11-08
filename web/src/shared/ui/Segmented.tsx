import { motion } from "framer-motion";

export interface Option {
  id: string;
  label: string;
  note?: string;
}

/** A choice between views. The marker slides to the chosen one, so it is clear what changed. */
export function Segmented({ options, value, onChange, label }: { options: Option[]; value: string; onChange: (id: string) => void; label: string }) {
  return (
    <div className="segmented" role="radiogroup" aria-label={label}>
      {options.map((o) => {
        const on = o.id === value;
        return (
          <button key={o.id} role="radio" aria-checked={on} className={`segmented__option ${on ? "segmented__option--on" : ""}`} onClick={() => onChange(o.id)}>
            {on && <motion.span layoutId={`${label}-marker`} className="segmented__marker" transition={{ type: "spring", stiffness: 500, damping: 40 }} />}
            <span className="segmented__label">{o.label}</span>
            {o.note && <span className="segmented__note">{o.note}</span>}
          </button>
        );
      })}
    </div>
  );
}
