import React, { useState } from 'react';

const API_URL = process.env.REACT_APP_API_URL;

const ReportPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const downloadReport = async () => {
    try {
      setLoading(true);
      setError(null);

      const response = await fetch(`${API_URL}/reports/generate`, {
        method: 'GET',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        if (response.status === 401) {
          setError('Сессия истекла. Пожалуйста, войдите снова.');
          return;
        }
        throw new Error(`Ошибка сервера: ${response.status}`);
      }

      const { url } = await response.json();
      window.open(url, '_blank', 'noopener,noreferrer');

    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-gray-100">
      <div className="p-8 bg-white rounded-lg shadow-md">
        <h1 className="text-2xl font-bold mb-6">Usage Reports</h1>

        <button
          onClick={downloadReport}
          disabled={loading}
          className={`px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 ${
            loading ? 'opacity-50 cursor-not-allowed' : ''
          }`}
        >
          {loading ? 'Generating Report...' : 'Download Report'}
        </button>

        {error && (
          <div className="mt-4 p-4 bg-red-100 text-red-700 rounded">
            {error}
            {/* Опционально: кнопка повторного входа при 401 */}
            {error.includes('Сессия истекла') && (
              <button
                onClick={() => window.location.reload()}
                className="ml-4 px-3 py-1 bg-gray-500 text-white rounded hover:bg-gray-600"
              >
                Войти снова
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default ReportPage;