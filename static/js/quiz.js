/* NetQuest quiz engine: renders and grades lesson/module checks.
 * Deterministic grading happens on the server (/api/answer). */
(function () {
  "use strict";

  function payloadFor(block) {
    var qid = block.getAttribute("data-qid");
    var type = block.getAttribute("data-type") || "mcq";
    if (type === "mcq") {
      var chosen = -1;
      block.querySelectorAll("input[type=radio]").forEach(function (n) {
        if (n.checked) chosen = +n.value;
      });
      return { question_id: qid, answer: chosen };
    }
    if (type === "self") {
      var covered = [];
      block.querySelectorAll("input[type=checkbox]").forEach(function (n) {
        if (n.checked) covered.push(n.value);
      });
      var ta = block.querySelector("textarea");
      return { question_id: qid, covered: covered, text: ta ? ta.value : "" };
    }
    var area = block.querySelector("textarea");
    return { question_id: qid, text: area ? area.value : "" };
  }

  function renderResult(block, data) {
    var r = data.result;
    var fb = block.querySelector(".fb");
    var ok = r.correct || (r.percent !== undefined && r.percent >= 70);
    var html = '<div class="feedback ' + (ok ? "ok" : "bad") + '">';
    if (r.percent !== undefined && r.type !== "mcq") {
      html += "<h4>" + r.percent + "%";
      if (r.passed !== undefined) html += r.passed ? " — passed" : " — below the pass mark";
      html += "</h4>";
    } else {
      html += "<h4>" + (r.correct ? "Correct" : "Not quite") + "</h4>";
    }
    html += "<div>" + NetQuest.escape(r.feedback || "") + "</div>";
    if (r.percent !== undefined && !r.correct && r.type !== "mcq") {
      html += '<div class="mt8">' + NetQuest.escape(r.verdict || "") + "</div>";
    }
    html += "</div>";
    fb.innerHTML = html;

    if (block.getAttribute("data-type") === "mcq" && r.correct_answer) {
      block.querySelectorAll(".option").forEach(function (opt) {
        var input = opt.querySelector("input");
        if (!input) return;
        if (+input.value === +(r.correct_answer_index !== undefined ? r.correct_answer_index : -99)) {
          opt.classList.add("correct");
        }
      });
    }
    if (data.mastery) {
      var badge = document.getElementById("lessonMastery");
      if (badge) badge.textContent = data.mastery.mastery + "%";
    }
    if (data.xp) {
      document.querySelectorAll(".js-xp").forEach(function (n) { n.textContent = data.xp.xp; });
    }
  }

  function attachSubmit(block) {
    var btn = block.querySelector(".check-submit");
    if (!btn) return;
    btn.addEventListener("click", function () {
      btn.disabled = true;
      btn.textContent = "Checking…";
      NetQuest.post("/api/answer", payloadFor(block))
        .then(function (data) {
          renderResult(block, data);
          btn.textContent = "Checked";
        })
        .catch(function (err) {
          block.querySelector(".fb").innerHTML =
            '<div class="feedback bad">' + NetQuest.escape(err.message) + "</div>";
          btn.disabled = false;
          btn.textContent = "Try again";
        });
    });
  }

  document.querySelectorAll(".check-block").forEach(attachSubmit);

  /* Show the correct option key styling after a check. */
  document.querySelectorAll(".reveal-ref").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var ref = btn.parentElement.querySelector(".ref-block");
      if (!ref) return;
      ref.classList.toggle("hidden");
      btn.textContent = ref.classList.contains("hidden") ? "Show reference answer" : "Hide reference answer";
    });
  });

  /* Complete-lesson button on the lesson page. */
  var done = document.getElementById("lessonComplete");
  if (done) {
    done.addEventListener("click", function () {
      var lessonId = done.getAttribute("data-lesson");
      done.disabled = true;
      done.textContent = "Saving…";
      NetQuest.post("/api/lesson/" + lessonId + "/complete", {})
        .then(function () {
          done.textContent = "Lesson completed";
          var b = document.getElementById("lessonState");
          if (b) { b.textContent = "completed"; b.className = "badge ok"; }
          NetQuest.toast("Lesson marked complete");
        })
        .catch(function () {
          done.disabled = false;
          done.textContent = "Mark lesson complete";
        });
    });
  }
})();
