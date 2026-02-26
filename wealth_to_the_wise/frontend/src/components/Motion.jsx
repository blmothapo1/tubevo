/**
 * Reusable framer-motion wrappers for consistent, premium animations.
 * Apple-style: subtle, fast, purposeful — nothing gratuitous.
 */
import { motion } from 'framer-motion';

const ease = [0.25, 0.1, 0.25, 1]; // Apple's ease curve

/** Fade-in + slide up on mount — use for page-level containers */
export function FadeIn({ children, className = '', delay = 0, y = 10, ...props }) {
  return (
    <motion.div
      initial={{ opacity: 0, y }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay, ease }}
      className={className}
      {...props}
    >
      {children}
    </motion.div>
  );
}

/** Staggered children animation — wrap a list and each child auto-staggers */
export function StaggerContainer({ children, className = '', staggerDelay = 0.06, ...props }) {
  return (
    <motion.div
      initial="hidden"
      animate="visible"
      variants={{
        visible: {
          transition: {
            staggerChildren: staggerDelay,
          },
        },
      }}
      className={className}
      {...props}
    >
      {children}
    </motion.div>
  );
}

/** Individual child in a stagger container */
export function StaggerItem({ children, className = '', ...props }) {
  return (
    <motion.div
      variants={{
        hidden: { opacity: 0, y: 8 },
        visible: { opacity: 1, y: 0, transition: { duration: 0.25, ease } },
      }}
      className={className}
      {...props}
    >
      {children}
    </motion.div>
  );
}

/** Scale on hover — for interactive cards */
export function HoverLift({ children, className = '', scale = 1.01, ...props }) {
  return (
    <motion.div
      whileHover={{ scale }}
      whileTap={{ scale: 0.98 }}
      transition={{ duration: 0.15, ease }}
      className={className}
      {...props}
    >
      {children}
    </motion.div>
  );
}

/** Smooth scale on press — for buttons */
export function PressScale({ children, className = '', as = 'div', ...props }) {
  const Component = as === 'button' ? motion.button : motion.div;
  return (
    <Component
      whileHover={{ scale: 1.01 }}
      whileTap={{ scale: 0.97 }}
      transition={{ duration: 0.15, ease }}
      className={className}
      {...props}
    >
      {children}
    </Component>
  );
}
