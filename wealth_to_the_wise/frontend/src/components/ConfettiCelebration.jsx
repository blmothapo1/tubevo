// filepath: frontend/src/components/ConfettiCelebration.jsx
/**
 * Lightweight confetti burst for celebrating first video generation.
 *
 * Pure CSS/JS — no external library needed. Renders coloured particles
 * that float and fade, then auto-removes itself after the animation.
 *
 * 100% additive — no existing code is touched.
 */
import { useEffect, useState, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

const COLORS = ['#6366f1', '#8b5cf6', '#fbbf24', '#34d399', '#f472b6', '#60a5fa', '#fb923c'];
const PARTICLE_COUNT = 60;

function randomBetween(min, max) {
  return Math.random() * (max - min) + min;
}

function ConfettiParticle({ color, delay }) {
  const startX = randomBetween(20, 80); // vw
  const drift = randomBetween(-30, 30); // px horizontal drift
  const size = randomBetween(6, 12);
  const duration = randomBetween(2, 4);
  const rotation = randomBetween(0, 720);
  const shape = Math.random() > 0.5 ? 'rounded-full' : 'rounded-sm';

  return (
    <motion.div
      initial={{
        opacity: 1,
        y: -20,
        x: 0,
        rotate: 0,
        scale: 1,
      }}
      animate={{
        opacity: [1, 1, 0],
        y: [0, window.innerHeight * 0.5, window.innerHeight * 0.9],
        x: [0, drift * 0.5, drift],
        rotate: rotation,
        scale: [1, 1, 0.5],
      }}
      transition={{
        duration,
        delay,
        ease: [0.25, 0.1, 0.25, 1],
      }}
      className={`absolute ${shape}`}
      style={{
        left: `${startX}%`,
        top: -10,
        width: size,
        height: size * (Math.random() > 0.5 ? 1 : 2.5),
        backgroundColor: color,
        zIndex: 10000,
      }}
    />
  );
}

export default function ConfettiCelebration({ show, onDone }) {
  const [particles, setParticles] = useState([]);
  const timerRef = useRef(null);

  useEffect(() => {
    if (show) {
      const newParticles = Array.from({ length: PARTICLE_COUNT }, (_, i) => ({
        id: i,
        color: COLORS[i % COLORS.length],
        delay: randomBetween(0, 0.5),
      }));
      setParticles(newParticles);

      // Auto-remove after animation completes
      timerRef.current = setTimeout(() => {
        setParticles([]);
        onDone?.();
      }, 5000);
    }

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [show, onDone]);

  return (
    <AnimatePresence>
      {particles.length > 0 && (
        <div className="fixed inset-0 pointer-events-none z-[9998] overflow-hidden">
          {particles.map((p) => (
            <ConfettiParticle key={p.id} color={p.color} delay={p.delay} />
          ))}
        </div>
      )}
    </AnimatePresence>
  );
}
