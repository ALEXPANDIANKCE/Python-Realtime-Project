document.getElementById("loginForm").addEventListener("submit", function (e) {
    e.preventDefault();

    const username = document.getElementById("loginUsername").value;
    const password = document.getElementById("loginPassword").value;

    const storedUsername = localStorage.getItem("username");
    const storedPassword = localStorage.getItem("password");

    const errorMsg = document.getElementById("errorMsg");

    if (username === storedUsername && password === storedPassword) {
        window.location.href = "/dashboard";
    } else {
        errorMsg.textContent = "❌ Invalid username or password!";
    }
});