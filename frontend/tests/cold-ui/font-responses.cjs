// Next's internal font-fetch test hook prevents network-dependent Google Fonts
// requests. These behavior tests deliberately use the browser's system fonts.
module.exports = new Proxy({}, {
  get: (_target, url) => {
    const family = String(url).includes('Geist+Mono') ? 'Geist Mono' : 'Geist';
    return `@font-face { font-family: '${family}'; src: local('Arial'); font-display: swap; }`;
  },
});
