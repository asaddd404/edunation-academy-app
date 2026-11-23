<template>
  <!-- Capped and centred on wide monitors: at 1920px full-width pages
       stretched homework cards and request rows to ~1900px, leaving action
       buttons a screen away from the name they act on. The landing page
       already caps its sections at 80rem; this keeps the app in step. -->
  <div class="mx-auto w-full max-w-[90rem] px-4 py-6 sm:px-6 lg:px-10 lg:py-8 xl:px-14">
    <slot />
  </div>
</template>
