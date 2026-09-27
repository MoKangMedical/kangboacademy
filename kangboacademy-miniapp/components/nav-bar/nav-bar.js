Component({
 properties: {
 title: {
 type: String,
 value: '康波研究院'
 },
 showBack: {
 type: Boolean,
 value: false
 }
 },

 data: {
 statusBarHeight: 20,
 navBarHeight: 44
 },

 lifetimes: {
 attached() {
 const app = getApp();
 this.setData({
 statusBarHeight: app.globalData.statusBarHeight || 20,
 navBarHeight: app.globalData.navBarHeight || 44
 });
 }
 },

 methods: {
 onBack() {
 wx.navigateBack({ delta: 1 });
 }
 }
});
