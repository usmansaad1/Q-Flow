// WHAT THIS FILE IS FOR: settings for PostCSS, the tool that prepares the site's styling files.
// It switches on Tailwind, the styling toolkit the pages use for colours, spacing and layout.
// The build reads this file automatically.

// The list of styling add ons to run. Only Tailwind is used.
const config = {
  plugins: {
    "@tailwindcss/postcss": {},
  },
};

export default config;
