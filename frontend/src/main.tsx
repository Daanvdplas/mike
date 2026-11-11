import './style.css';
import { createRoot } from 'react-dom/client';
import { App } from './app';
import { createApiClient, createMockClient } from './client';

const isMock = import.meta.env.VITE_API_MODE !== 'api';
const client = isMock ? createMockClient() : createApiClient(import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000');
createRoot(document.querySelector<HTMLElement>('#app')!).render(<App client={client} isMock={isMock} />);
