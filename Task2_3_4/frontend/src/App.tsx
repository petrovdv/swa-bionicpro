import React from 'react';
import { useAuth } from './hooks/useAuth';
import ReportPage from './components/ReportPage';

const App: React.FC = () => {
  const { authed, login } = useAuth();

  if (authed === null) return <div>Загрузка...</div>;
  if (!authed) { 
    login(); // запускаем редирект
    return <div>Перенаправление на вход...</div>; 
  }

  return (
      <div className="App">
        <ReportPage/>
      </div>
  );
};

export default App;