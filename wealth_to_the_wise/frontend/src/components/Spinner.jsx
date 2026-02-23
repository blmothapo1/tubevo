import { Loader2 } from 'lucide-react';

export default function Spinner({ className = '' }) {
  return <Loader2 className={`animate-spin text-brand-400 ${className}`} size={24} />;
}
