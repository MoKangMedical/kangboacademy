// Persist the last submitted draft per account/lesson, including after a timeout.
function practiceSubmissionPayload(lesson, answers, reflection) {
 const sortedAnswers = {};
 Object.keys(answers || {}).sort().forEach(key => {
  Object.defineProperty(sortedAnswers, key, { value: answers[key], enumerable: true });
 });
 return { lesson, answers: sortedAnswers, reflection: reflection || '' };
}

function withSubmissionId(payload) {
 const user = wx.getStorageSync('userInfo');
 const account = user && user.id != null ? String(user.id) : (wx.getStorageSync('token') || 'anonymous');
 const storageKey = `practice-submission-v1:${JSON.stringify([account, payload.lesson])}`;
 const fingerprint = JSON.stringify(payload);
 const previous = wx.getStorageSync(storageKey);
 if (previous && previous.fingerprint === fingerprint && previous.id) {
  return { ...payload, submission_id: previous.id };
 }
 const randomPart = () => Math.floor(Math.random() * 0x100000000).toString(16).padStart(8, '0');
 const id = `practice-${Date.now().toString(36)}-${randomPart()}${randomPart()}${randomPart()}`;
 // Fail before sending if persistence fails, rather than lose the retry ID.
 wx.setStorageSync(storageKey, { fingerprint, id });
 return { ...payload, submission_id: id };
}

module.exports = { practiceSubmissionPayload, withSubmissionId };
