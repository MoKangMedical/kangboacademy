Component({
 properties: {
 num: { type: Number, value: 1 },
 title: { type: String, value: '' },
 desc: { type: String, value: '' },
 diffLabel: { type: String, value: '入门' },
 diffColor: { type: String, value: 'tag-green' },
 time: { type: String, value: '30分钟' },
 lesson: { type: String, value: '' },
 free: { type: Boolean, value: false },
 locked: { type: Boolean, value: false }
 },

 methods: {
 onTap() {
 if (this.properties.lesson) {
 wx.navigateTo({
 url: `/pages/course-detail/course-detail?lesson=${this.properties.lesson}&title=${encodeURIComponent(this.properties.title)}`
 });
 }
 this.triggerEvent('tap', { lesson: this.properties.lesson, title: this.properties.title });
 }
 }
});
