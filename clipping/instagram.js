/* Tokens stay server-side; the browser only navigates to Instagram consent. */
(() => {
  const byId=id=>document.getElementById(id),base='/api/v1/clipping/accounts/instagram';
  let checking=false,connecting=false,configured=false,oauthConfigured=false,expired=false;
  const callbackMessages={connected:'Instagram authorization completed. Account access is shown below.',
    oauth_state_invalid:'The Instagram login expired or could not be validated. Connect again.',
    oauth_failed:'Instagram authorization could not be completed. Connect again after checking the app setup.',
    oauth_not_configured:'Instagram connection setup is incomplete.',
    network_unavailable:'Instagram could not be reached. Check the connection, then connect again.',
    access_denied:'Instagram authorization was declined. Connect again when you are ready.',
    token_invalid:'Instagram refused the token. Connect again to replace it.',
    token_expired:'The Instagram token expired. Reconnect Instagram to restore access.',
    response_invalid:'Instagram returned an unexpected account response. Connect again later.',
    provider_unavailable:'Instagram is temporarily unavailable. Connect again later.',
    rate_limited:'Instagram limited this request. Wait before connecting again.',
    configuration_error:'Check the Instagram app configuration before connecting again.'};
  const callbackCode=new URLSearchParams(window.location.search).get('instagram');
  let callbackMessage=callbackMessages[callbackCode] || '';
  const titles={not_configured:'Setup needed',configuration_error:'Check account configuration',
    unverified:'Saved · unverified',verified:'Account verified',profile_verified:'Profile verified',
    account_mismatch:'Account ID mismatch',network_unavailable:'Connection unavailable',
    token_invalid:'Token needs replacement',token_expired:'Account authorization expired',access_denied:'Access refused',rate_limited:'Wait before retrying',
    provider_unavailable:'Instagram unavailable',response_invalid:'Verification incomplete'};
  async function request(action='') {
    const response=await fetch(base+(action ? '/'+action : ''),action ?
      {method:'POST',headers:{'Content-Type':'application/json'},body:'{}'} : {cache:'no-store'});
    const result=await response.json();
    if(!response.ok)throw new Error(result.message || 'The workspace could not complete the Instagram check. Try again.');
    return result;
  }
  function buttons() {
    byId('instagram-verify').disabled=checking || connecting || !configured || expired;
    byId('instagram-connect').disabled=checking || connecting || !oauthConfigured;
    byId('instagram-connect').textContent=connecting ? 'Opening Instagram…' : configured ? 'Reconnect Instagram' : 'Connect Instagram';
  }
  function render(state) {
    configured=state.configured;
    oauthConfigured=state.oauth_configured;
    expired=state.token_expired===true;
    byId('instagram-status').textContent=titles[state.status] || 'Verification incomplete';
    byId('instagram-identity').textContent=state.account_id ?
      `${state.username ? '@'+state.username+' · ' : ''}Account ID: ${state.account_id}${state.returned_account_id && state.returned_account_id!==state.account_id ? ' · Token account: '+state.returned_account_id : ''}` : 'No Instagram account ID is configured.';
    byId('instagram-permissions').textContent=state.content_publish_permission===true ?
      'Content publishing permission granted. Posting remains disabled.' : state.content_publish_permission===false ?
      'Content publishing permission not granted. Posting remains disabled.' : 'Publishing permission is unverified. Posting remains disabled.';
    byId('instagram-checked').textContent=state.last_checked_at ? `Last check: ${new Date(state.last_checked_at).toLocaleString()}.` :
      expired ? 'The previous account access is no longer current.' : 'No account verification has completed yet.';
    byId('instagram-expiry').textContent=!configured ? 'Token expiry will appear after account authorization.' :
      state.token_expires_at ? `Access ${expired ? 'expired' : 'expires'}: ${new Date(state.token_expires_at).toLocaleString()}.${expired ? ' Reconnect Instagram to restore access.' : ''}` :
      'Token expiry is unknown. Verify account access when needed.';
    byId('instagram-message').textContent=callbackCode==='connected' && !['verified','profile_verified'].includes(state.status) ?
      state.message : callbackMessage || state.message;
    byId('instagram-oauth-note').textContent=oauthConfigured ?
      'Connect opens Instagram so you can authorize this workspace. Posting remains disabled.' :
      'Instagram app setup is incomplete. A saved account can still be verified.';
    buttons();
  }
  async function refresh() {
    if(checking || connecting)return;
    try {render(await request());}catch(error){byId('instagram-message').textContent=error.message;}
  }
  byId('instagram-verify').onclick=async()=>{
    if(checking || connecting)return;checking=true;callbackMessage='';buttons();
    byId('instagram-verify').textContent='Checking Instagram…';
    byId('instagram-status').textContent='Verifying account access…';
    try {render(await request('verify'));}catch(error){byId('instagram-message').textContent=error.message;}
    finally {checking=false;byId('instagram-verify').textContent='Verify Instagram access';buttons();}
  };
  byId('instagram-connect').onclick=async()=>{
    if(checking || connecting)return;connecting=true;callbackMessage='';buttons();
    byId('instagram-message').textContent='Opening Instagram authorization…';
    try {const result=await request('connect');window.location.assign(result.authorization_url);}
    catch(error){byId('instagram-message').textContent=error.message;}
    finally {connecting=false;buttons();}
  };
  window.instagramAccount={refresh};refresh();setInterval(refresh,30000);
})();
