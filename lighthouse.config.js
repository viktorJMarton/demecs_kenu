module.exports = {
  extends: 'lighthouse:default',
  settings: {
    emulatedFormFactor: 'mobile',
    onlyCategories: ['performance', 'accessibility', 'best-practices', 'seo'],
  }
};
