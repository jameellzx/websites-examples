(function(){
    var timeout = null;
    function stretchedSections() {
        clearTimeout(window.stretchedTimmer);
        window.stretchedTimmer = setTimeout(() => {
            let sections = document.querySelectorAll(".ecom-core.ecom-section"),
                swipers = document.querySelectorAll(".ecom-swiper-container"),
                ecomSections = document.querySelectorAll(".ecom-sections"),
                windowWidth = window.innerWidth;
            if (sections.length > 0) {
                ecomSections.forEach((s) => {
                    s.style.width = "";
                });
                let //ssections = document.querySelectorAll('.ecom-core.ecom-section.ecom-section__stretched'),
                    //pwidth = ecomSections.offsetWidth,
                    mleft = (windowWidth - ecomSections[0].offsetWidth) / 2;
                sections.forEach((section) => {
                    if (section.classList.contains("ecom-section__stretched")) {
                        section.style.width = windowWidth + "px";
                        section.style.marginLeft = -mleft + "px";
                    } else {
                        section.style.width = "";
                        section.style.marginLeft = "";
                    }
                });
                /*if (ssections.length > 0) {
                    ecomSections.style.width = pwidth + 'px';
                } else {
                    ecomSections.style.width = '';
                }*/
            }
            if (swipers.length > 0) {
                swipers.forEach((swiper) => {
                    if (swiper.EComSwiper) {
                        swiper.EComSwiper.update();
                    }
                });
            }
        }, 50);
    }
    function isVisible(ele) {
        const { top, bottom } = ele.getBoundingClientRect();
        const vHeight = window.innerHeight || document.documentElement.clientHeight;
        return (top > 0 || bottom > 0) && top < vHeight;
    }
    function handleScroll(){
        let videos = document.querySelectorAll(".ecom-sections .ecom-video-background");
        videos.forEach(function(video){
            if(video.dataset.playPauseInview === 'true')
            {
                if(isVisible(video))
                {
                    video.play();
                }
                else 
                {
                    video.pause();
                }
            }
        });
        
    }
    stretchedSections();
    window.addEventListener("resize", stretchedSections);
    window.addEventListener("load", stretchedSections);
    window.addEventListener('scroll', function(){
        clearTimeout(timeout);
        
        timeout = setTimeout(handleScroll, 500);
    });
    
})();