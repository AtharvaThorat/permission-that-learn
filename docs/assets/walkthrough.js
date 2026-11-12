(() => {
  let grant = false, step = 1;
  const get = id => document.getElementById(id);
  function show(title, text, log, resource = 'notes-7') {
    get('step-count').textContent = `STEP ${step++}`;
    get('demo-title').textContent = title;
    get('demo-explanation').textContent = text;
    get('demo-command').textContent = `get_file_by_id(${JSON.stringify({file_id: resource})})`;
    get('grant-state').textContent = grant ? 'Illustrative user-0 grant: exact request + notes-7 + arguments + trusted evidence + current policy/schema. TTL 24 hours. Revocable.' : 'No reusable permission.';
    const li = document.createElement('li'); li.textContent = log; get('demo-log').append(li);
  }
  get('approve-once').onclick = () => show('One-time approval', 'The exact action can execute after rechecks. Approval does not create or extend a reusable grant.', 'Approve once → recheck → simulated dispatch.');
  get('grant').onclick = () => { grant = true; show('Explicit permission issued', 'A reusable exact-scope permission now exists. It is separate from approval of the pending action.', 'Operator explicitly grants scope; no automatic dispatch.'); };
  get('reject').onclick = () => { grant = false; show('Request rejected', 'Withhold dispatch and revoke matching reusable permission.', 'Reject → no execution → matching grant revoked.'); };
  get('repeat').onclick = () => show('The exact request returns', grant ? 'Wall PASS, Laya ASK, valid grant. In this illustrative branch the active learner selects USE_EXISTING_GRANT. Rechecks pass, then dispatch.' : 'Wall PASS and Laya ASK again. Without a grant, previous approval does not establish permission.', grant ? 'Grant match → illustrative reuse choice → recheck → simulated dispatch.' : 'No grant → ASK_USER → withheld.');
  get('changed').onclick = () => show('A different resource', 'The notes-7 grant does not cover notes-8. Laya ASK stays pending; the learner cannot widen authority.', 'Resource changed → no matching grant → withheld.', 'notes-8');
  get('revoke').onclick = () => { grant = false; show('Permission revoked', 'The next matching request requires approval again. Revocation invalidates grant-derived authorization.', 'Revoke → repeat → ASK_USER → withheld.'); };
  get('blocked').onclick = () => show('Fixed boundary denies', 'A Wall denial stops execution before Laya or permission reuse can authorize it.', 'Wall BLOCK → withheld; grant cannot override.');
  get('reset').onclick = () => { grant = false; step = 1; get('demo-log').replaceChildren(); show('First request', 'Laya: ASK. No reusable grant exists. The action is withheld.', 'Wall PASS → Laya ASK → awaiting user.'); };
})();
