/** Keep verification builds separate from an already running development server. */
export default {
  distDir: process.env.AGENTOS_NEXT_DIST_DIR || '.next',
};
