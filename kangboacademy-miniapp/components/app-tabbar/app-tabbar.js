Component({
 data: {
 activeKey: 'home',
 tabs: [
 {
 key: 'home',
 text: '首页',
 path: '/pages/index/index',
 icon: '/assets/icons/home.png',
 activeIcon: '/assets/icons/home-active.png'
 },
 {
 key: 'courses',
 text: '主干课程',
 path: '/pages/courses/courses',
 icon: '/assets/icons/course.png',
 activeIcon: '/assets/icons/course-active.png'
 },
 {
 key: 'bookCourses',
 text: '书目课程',
 path: '/pages/book-courses/book-courses',
 icon: '/assets/icons/book.png',
 activeIcon: '/assets/icons/book-active.png'
 },
 {
 key: 'tools',
 text: '工具',
 path: '/pages/tools/index',
 icon: '/assets/icons/tool.png',
 activeIcon: '/assets/icons/tool-active.png'
 },
 {
 key: 'user',
 text: '我的',
 path: '/pages/user/user',
 icon: '/assets/icons/user.png',
 activeIcon: '/assets/icons/user-active.png'
 }
 ]
 },

 lifetimes: {
 attached() {
 this.syncActive();
 }
 },

 pageLifetimes: {
 show() {
 this.syncActive();
 }
 },

 methods: {
 syncActive() {
 const pages = getCurrentPages();
 const route = pages.length ? pages[pages.length - 1].route : '';
 let activeKey = 'home';

 if (route === 'pages/course-detail/course-detail') {
 const options = pages.length ? (pages[pages.length - 1].options || {}) : {};
 activeKey = /^book\d+\.html$/.test(options.lesson || '') ? 'bookCourses' : 'courses';
 } else if (route === 'pages/courses/courses') {
 activeKey = 'courses';
 } else if (route === 'pages/book-courses/book-courses') {
 activeKey = 'bookCourses';
 } else if (route.indexOf('pages/tools/') === 0) {
 activeKey = 'tools';
 } else if (
 route === 'pages/user/user' ||
 route === 'pages/membership/membership' ||
 route === 'pages/favorites/favorites' ||
 route === 'pages/notes/notes'
 ) {
 activeKey = 'user';
 }

 if (activeKey !== this.data.activeKey) {
 this.setData({ activeKey });
 }
 },

 switchTab(e) {
 const path = e.currentTarget.dataset.path;
 if (!path) return;
 wx.switchTab({ url: path });
 }
 }
});
