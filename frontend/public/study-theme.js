(()=>{
 let theme;try{theme=localStorage.getItem('pyq-theme')}catch{}
 if(!['dark','light'].includes(theme))theme=window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';
 const apply=()=>{document.documentElement.dataset.theme=theme;document.documentElement.dataset.bsTheme=theme;const button=document.getElementById('study-theme-toggle');if(button){button.textContent=theme==='dark'?'☀ Light mode':'☾ Dark mode';button.setAttribute('aria-label','Switch to '+(theme==='dark'?'light':'dark')+' theme');button.setAttribute('aria-pressed',String(theme==='dark'))}};
 apply();document.addEventListener('DOMContentLoaded',()=>{apply();document.getElementById('study-theme-toggle')?.addEventListener('click',()=>{theme=theme==='dark'?'light':'dark';try{localStorage.setItem('pyq-theme',theme)}catch{}apply()})});
})();
