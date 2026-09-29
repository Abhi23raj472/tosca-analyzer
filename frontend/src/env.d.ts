/// <reference types="vite/client" />
declare const __DEMO_BUILD__: boolean;
declare module "*.xml?raw" {
  const content: string;
  export default content;
}
