/* "Install app" button (PWA). Appears only when the browser says the site can be installed. */
(function(){
  'use strict';
  var deferred=null;
  function btn(){return document.getElementById('installBtn');}
  function make(){
    if(btn())return btn();
    var host=document.getElementById('themeBtn');
    if(!host||!host.parentNode)return null;
    var b=document.createElement('button');
    b.type='button';b.id='installBtn';b.className=host.className;b.hidden=true;
    b.setAttribute('aria-label','نصب بازارنما روی دستگاه');b.title='نصب بازارنما روی دستگاه';b.textContent='⤓';
    host.parentNode.insertBefore(b,host);
    b.addEventListener('click',function(){
      if(!deferred)return;
      deferred.prompt();
      deferred.userChoice.then(function(){deferred=null;b.hidden=true;}).catch(function(){});
    });
    return b;
  }
  window.addEventListener('beforeinstallprompt',function(e){
    e.preventDefault();deferred=e;
    var b=make();if(b)b.hidden=false;
  });
  window.addEventListener('appinstalled',function(){deferred=null;var b=btn();if(b)b.hidden=true;});
})();
