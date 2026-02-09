/**
 * Simple auth: token in localStorage, login screen vs app screen.
 */
const Auth = {
    KEY: 'document_scraper_token',

    getToken() {
        return localStorage.getItem(this.KEY);
    },

    setToken(token) {
        if (token) localStorage.setItem(this.KEY, token);
        else localStorage.removeItem(this.KEY);
    },

    getAuthHeaders() {
        const token = this.getToken();
        return token ? { 'Authorization': `Bearer ${token}` } : {};
    },

    showLogin() {
        document.getElementById('loginScreen').style.display = 'flex';
        document.getElementById('appScreen').style.display = 'none';
    },

    showApp() {
        document.getElementById('loginScreen').style.display = 'none';
        document.getElementById('appScreen').style.display = 'flex';
    },

    async checkAuth() {
        const token = this.getToken();
        if (!token) return false;
        try {
            const r = await fetch('/api/auth/status', { headers: this.getAuthHeaders() });
            return r.ok;
        } catch (e) {
            return false;
        }
    },

    logout() {
        this.setToken(null);
        this.showLogin();
    }
};
