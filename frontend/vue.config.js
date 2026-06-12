// frontend/vue.config.js
const { defineConfig } = require('@vue/cli-service');

module.exports = defineConfig({
  transpileDependencies: true,
  devServer: {
    host: '0.0.0.0',
    // port: Number(process.env.PORT || 3000),
    port: Number(process.env.PORT || 3000),
    allowedHosts: 'all'
  },
  css: {
    loaderOptions: {
      css: {
        sourceMap: true
      }
    }
  }
});
