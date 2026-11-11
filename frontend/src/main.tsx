import './style.css';
import { createRoot } from 'react-dom/client';
import { App } from './app';
import { createSearchRuntime } from './runtime';

const { isMock, client } = createSearchRuntime(import.meta.env.VITE_API_MODE, import.meta.env.VITE_API_BASE_URL || undefined);
createRoot(document.querySelector<HTMLElement>('#app')!).render(<App client={client} isMock={isMock} />);
