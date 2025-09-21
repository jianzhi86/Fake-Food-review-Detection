document.addEventListener('DOMContentLoaded', () => {
  const taskList = document.getElementById('taskList');
  const addTaskBtn = document.getElementById('addTaskBtn');
  const modal = document.getElementById('resultsModal');
  const closeButton = document.querySelector('.close-button');
  const companyNameSpan = document.getElementById('companyName');
  const modalResultsContainer = document.getElementById('modalResults');
  const pastResultsList = document.getElementById('pastResultsList');

  const MAX_TOTAL_TASKS = 3;

  function updateAddTaskButtonState() {
    const currentTaskCount = document.querySelectorAll('.task-block').length;
    if (currentTaskCount >= MAX_TOTAL_TASKS) {
      addTaskBtn.disabled = true;
      addTaskBtn.textContent = 'Maximum of 3 inputs reached';
    } else {
      addTaskBtn.disabled = false;
      addTaskBtn.textContent = '+ Add Another';
    }
  }

  function createTaskBlock(isFirst = false) {
    const taskDiv = document.createElement('div');
    taskDiv.className = 'task-block';
    
    taskDiv.innerHTML = `
      <div class="task-input-group">
        <input type="text" class="url-input" placeholder="Paste Google Maps URL here">
        <div class="task-actions">
          <button class="detect-btn">Detect</button>
          <button class="remove-btn" style="${isFirst ? 'display:none;' : ''}">✖</button>
        </div>
      </div>
      <div class="progress-container" style="display:none;">
        <div class="progress-bar-background">
          <div class="progress-bar-foreground"></div>
        </div>
        <p class="progress-status">Scraping reviews...</p>
      </div>
    `;

    const detectBtn = taskDiv.querySelector('.detect-btn');
    const urlInput = taskDiv.querySelector('.url-input');
    const deleteBtn = taskDiv.querySelector('.remove-btn');
    const progressContainer = taskDiv.querySelector('.progress-container');
    const progressBar = taskDiv.querySelector('.progress-bar-foreground');
    const progressStatus = taskDiv.querySelector('.progress-status');

    let pollingInterval = null;

    detectBtn.addEventListener('click', async () => {
      const url = urlInput.value;
      if (!url) {
        alert("Please enter a URL first!");
        return;
      }
      
      detectBtn.disabled = true;
      urlInput.disabled = true;
      deleteBtn.disabled = true;

      progressContainer.style.display = 'block';
      progressBar.style.width = '0%';
      progressStatus.textContent = 'Submitting job to server...';

      try {
        const startResponse = await fetch("http://127.0.0.1:5000/detect", {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url }),
        });
        if (!startResponse.ok) {
          const errorData = await startResponse.json();
          throw new Error(errorData.error || "Failed to start job.");
        }
        const { job_id } = await startResponse.json();

        pollingInterval = setInterval(async () => {
          try {
            const resultResponse = await fetch(`http://127.0.0.1:5000/results/${job_id}`);
            if (!resultResponse.ok) throw new Error("Failed to fetch job status.");
            const data = await resultResponse.json();
            const { percentage, message } = data.progress;
            progressStatus.textContent = message || 'Processing...';
            progressBar.style.width = `${percentage || 5}%`;

            if (data.status === 'complete' || data.status === 'error') {
              clearInterval(pollingInterval);
              pollingInterval = null;
              
              if (data.status === 'complete') {
                progressBar.style.width = '100%';
                progressStatus.textContent = 'Analysis Complete!';
                handleSuccess(data.result);
                fetchPastResults();

                // *** FIX: Automatically remove the completed task block after a short delay ***
                setTimeout(() => {
                    taskDiv.remove();
                    updateAddTaskButtonState(); // Update the button state after removing
                }, 2000); // Wait 2 seconds so the user can see the "Complete!" message

              } else {
                throw new Error(data.result || "Analysis failed.");
              }
              
            }
          } catch (err) {
            clearInterval(pollingInterval);
            pollingInterval = null;
            progressStatus.textContent = `Error: ${err.message}`;
            progressStatus.style.color = 'red';
            
            // Re-enable all buttons on error so the user can try again or delete
            detectBtn.disabled = false;
            urlInput.disabled = false;
            deleteBtn.disabled = false;
          }
        }, 2000);
      } catch (err) {
        alert(`Error: ${err.message}`);
        detectBtn.disabled = false;
        urlInput.disabled = false;
        deleteBtn.disabled = false;
        progressContainer.style.display = 'none';
      }
    });

    deleteBtn.addEventListener('click', () => {
      taskDiv.remove();
      updateAddTaskButtonState();
    });

    taskList.appendChild(taskDiv);
  }

  // --- Handle review results in modal ---
  const handleSuccess = (results) => {
    if (results && Array.isArray(results.reviews)) {
      companyNameSpan.textContent = results.company_name || 'Restaurant Results';
      modalResultsContainer.innerHTML = '';
      if (results.reviews.length === 0) {
        modalResultsContainer.innerHTML = '<p class="info-message">No reviews found.</p>';
      } else {
        results.reviews.forEach(review => {
          const isSuspicious = review.prediction === 'Fake';
          const card = document.createElement('div');
          card.className = 'review-card';
          card.style.borderColor = isSuspicious ? '#e74c3c' : '#2ecc71';
          card.style.borderWidth = '2px';
          card.innerHTML = `
            <div class="review-header">
              <img src="${review.avatar}" alt="${review.author}" class="profile-pic">
              <div class="reviewer-info">
                <span class="reviewer-name">${review.author}</span>
                <span class="review-date">${new Date(review.review_date).toLocaleDateString()}</span>
              </div>
            </div>
            <div class="review-rating">${'⭐'.repeat(Math.round(review.rating))}</div>
            <div class="review-description"><p>${review.text || 'No review text.'}</p></div>
            <div class="review-details">
              <span>Likes: ${review.likes}</span>
              <span style="color: ${isSuspicious ? 'red' : 'green'}; font-weight: bold;">
                ${isSuspicious ? 'Suspicious' : 'Likely Genuine'}
              </span>
            </div>`;
          modalResultsContainer.appendChild(card);
        });
      }
      modal.style.display = 'block';
    }
  };

  // --- Past results handling ---
  const fetchPastResults = async () => {
    try {
      const response = await fetch("http://127.0.0.1:5000/past_results");
      if (!response.ok) {
        pastResultsList.innerHTML = '<p style="color: red;">Could not load past results.</p>';
        return;
      }
      const results = await response.json();
      if (results.length === 0) {
        pastResultsList.innerHTML = '<p>No past results found.</p>';
        return;
      }

      let tableHTML = `
        <table class="past-results-table">
          <thead><tr><th>Restaurant</th><th>Date</th><th>Actions</th></tr></thead>
          <tbody>
      `;
      results.forEach(r => {
        const resultDate = new Date(r.date).toLocaleString();
        tableHTML += `
          <tr>
            <td>${r.name}</td>
            <td>${resultDate}</td>
            <td class="actions">
              <button class="view-btn" data-key="${r.s3_key}">View</button>
              <button class="delete-btn" data-key="${r.s3_key}">×</button>
            </td>
          </tr>`;
      });
      tableHTML += '</tbody></table>';
      pastResultsList.innerHTML = tableHTML;
    } catch (err) {
      console.error(err);
      pastResultsList.innerHTML = '<p style="color: red;">Could not load past results.</p>';
    }
  };
  
  pastResultsList.addEventListener('click', async (event) => {
    const target = event.target;
    if (target.tagName !== 'BUTTON') return;
    const s3Key = target.dataset.key;
    if (!s3Key) return;

    if (target.classList.contains('view-btn')) {
      const s3Url = `https://fake-food-review.s3.ap-southeast-1.amazonaws.com/${s3Key}`;
      try {
        const response = await fetch(s3Url);
        if (!response.ok) throw new Error(`S3 error: ${response.status}`);
        const resultsData = await response.json();
        handleSuccess(resultsData);
      } catch (err) {
        alert(`Error: ${err.message}`);
      }
    }
    if (target.classList.contains('delete-btn')) {
      if (confirm("Delete this report?")) {
        try {
          const res = await fetch("http://127.0.0.1:5000/delete_report", {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ key: s3Key }),
          });
          if (!res.ok) throw new Error("Failed to delete.");
          fetchPastResults();
        } catch (err) {
          alert(`Error: ${err.message}`);
        }
      }
    }
  });

  // --- Modal close ---
  closeButton.addEventListener('click', () => modal.style.display = 'none');
  window.addEventListener('click', (e) => { if (e.target === modal) modal.style.display = 'none'; });

  // --- Init ---
  createTaskBlock(true);
  updateAddTaskButtonState();

  addTaskBtn.addEventListener('click', () => {
    const currentTaskCount = document.querySelectorAll('.task-block').length;
    if (currentTaskCount >= MAX_TOTAL_TASKS) {
      alert(`You can only have a maximum of ${MAX_TOTAL_TASKS} inputs at a time.`);
      return;
    }
    createTaskBlock(false);
    updateAddTaskButtonState();
  });

  fetchPastResults();
});