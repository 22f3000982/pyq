// This script is included only on an eligible public study paper, never in the SPA.
// No Google ad request is made until a certified TCF CMP reports consent.
const slot=document.getElementById('study-ad');
let loaded=false;
if(slot&&typeof window.__tcfapi==='function')window.__tcfapi('addEventListener',2,(tc,ok)=>{
 if(!ok||!['tcloaded','useractioncomplete'].includes(tc?.eventStatus))return;
 if(loaded){if(!tc.purpose?.consents?.[1]||!tc.vendor?.consents?.[755])window.location.reload();return;}
 // Require affirmative consent even outside regulated regions (fail closed).
 if(!tc.purpose?.consents?.[1]||!tc.vendor?.consents?.[755])return;
 loaded=true;slot.hidden=false;
 const ad=document.createElement('ins');ad.className='adsbygoogle';ad.style.display='block';
 ad.dataset.adClient=slot.dataset.publisher;ad.dataset.adSlot=slot.dataset.slot;ad.dataset.adFormat='auto';ad.dataset.fullWidthResponsive='true';slot.appendChild(ad);
 const script=document.createElement('script');script.async=true;script.crossOrigin='anonymous';script.src='https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client='+encodeURIComponent(slot.dataset.publisher);
 script.onload=()=>{(window.adsbygoogle=window.adsbygoogle||[]).push({})};script.onerror=()=>{slot.hidden=true};document.head.appendChild(script);
});
