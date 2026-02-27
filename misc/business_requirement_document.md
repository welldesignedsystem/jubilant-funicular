# Business Requirements Document
## Shipyard Hull Fabrication & Assembly — Project Management System

**Document Version:** 1.0
**Status:** Draft
**Organization:** [Shipyard Name]
**Prepared By:** [Lead PM Name]
**Date:** [Date]

---

## 1. Executive Summary

This document defines the business requirements for a web-based project management system designed to support the planning, tracking, and governance of hull fabrication and assembly projects at a shipyard. The system must provide end-to-end visibility across all configurable project phases — from initial design and material procurement through fabrication, structural erection, testing, finishing, and vessel launch — while enforcing rigorous change control and baseline management practices aligned with project management best practices.

---

## 2. Business Objectives

- Provide a centralized, Gantt-based project tracking interface that accommodates a variable number of phases and stages tailored to each hull project.
- Enable formal baseline management with versioned snapshots and a full audit trail of all approved changes to scope, schedule, and cost.
- Support real-time progress tracking with deviation reporting against the approved project baseline.
- Enforce a structured change control process requiring documented justification, impact analysis, and formal approval before any baseline modification.
- Facilitate transparent and accountable stakeholder communication through systematically maintained notification logs.

---

## 3. Scope

### 3.1 In Scope

The system shall manage all phases of a configurable hull fabrication and assembly lifecycle. Phases and their constituent stages are project-specific and may be added, removed, or reordered by authorized users. A typical project may include phases such as:

- Design & Preparation
- Fabrication Preparation
- Material Preparation
- Sub-Assembly
- Block Assembly
- Grand Assembly
- Erection & Assembly
- Welding & Joining
- Testing & Validation
- Finishing
- Launch Preparation & Launch

The system must remain fully functional regardless of the number of phases or stages configured for a given project.

### 3.2 Out of Scope

- Post-launch outfitting and sea trial activities
- Financial cost management and procurement vendor relationship management
- Integration with external ERP or supply chain systems (unless separately specified)

---

## 4. Stakeholders

The system shall support multiple stakeholder roles. The roles below are representative and should be configurable per project:

| Role | Responsibilities |
|------|-----------------|
| Lead Project Manager | Owns the project schedule, initiates baseline changes, manages change requests |
| Baseline Approver | Reviews and approves or rejects all baseline change requests |
| Owner Representative | Provides sign-off on scope changes; represents the vessel owner's interests |
| Procurement Lead | Manages material delivery status and flags supplier-related delays |
| QA / Classification Officer | Certifies inspection and testing stage completions |

---

## 5. Functional Requirements

### 5.1 Phase & Stage Configuration

The system shall allow authorized users to define, add, reorder, and remove project phases and their constituent stages without requiring system-level changes. Each stage shall be associated with a parent phase and shall maintain its own schedule, status, and progress data independently. Dependencies between stages (predecessor/successor relationships) shall be configurable per project.

For example, a project may define a "Sub-Assembly" phase containing stages such as Panel Line Sub-Assembly, Frame Sub-Assembly, and Sub-Assembly Inspection — or it may omit this phase entirely if not applicable to the vessel type.

### 5.2 Gantt Chart & Schedule Tracking

The system shall present all configured phases and stages in an interactive Gantt chart. For each stage, the following data shall be captured and displayed:

- Planned start and planned end dates
- Actual start and actual end dates (entered as work progresses)
- Baseline start and baseline end dates (locked at time of baseline approval)
- Planned, actual, and baseline durations (calculated automatically)
- Current status (e.g., Not Started, In Progress, Blocked, Completed)
- Progress percentage (0–100%)
- Free-text comments for context or issue notes

The Gantt chart shall visually distinguish stage statuses and clearly surface blocked or delayed stages. Dependency arrows between stages shall be rendered to show the critical path.

### 5.3 Overall Project Progress

The system shall calculate and display an overall project completion percentage derived from the progress of all active stages. Summary metrics shall include total planned duration, total actual duration to date, and total baseline duration, giving the project team an at-a-glance view of schedule health.

For example, if 8 of 30 stages are fully complete and several are in progress, the system should aggregate these into a single overall percentage that reflects the weighted state of the project.

### 5.4 Baseline Management

The system shall support formal project baseline management in line with PMI/PMP best practices. A baseline represents an approved, versioned snapshot of the project's planned schedule and serves as the reference against which actual and current planned dates are compared.

**Setting a Baseline:** Authorized users may set a new baseline at any point, capturing all current planned dates as the new approved reference. The system shall record the baseline version number, date, and the user who set it.

**Resetting a Baseline:** Users may reset the active baseline, replacing it with a newly approved set of planned dates following a formal change request approval.

**Baseline History:** All previous baselines shall be retained and selectable for historical review. A user should be able to view what the schedule looked like as of any previous approved baseline.

**Baseline Report:** The system shall generate a downloadable baseline report summarizing the current baseline, its history, and all associated deviations.

### 5.5 Change Control

No baseline modification shall be permitted without a formally submitted and approved change request. The change control process shall enforce the following workflow:

1. A user submits a change request specifying the change type (e.g., Initial Baseline, Delay, Major Scope Change), the reason for change, estimated schedule impact in days, the requesting user, and the designated approver.
2. The approver reviews the request and either approves or rejects it, with mandatory comments.
3. Upon approval, the baseline is updated and the change is logged in the audit trail.
4. Stakeholders impacted by the change are notified automatically.

The system shall prevent baseline changes from taking effect until the approval step is completed. Scope changes shall additionally require sign-off from the Owner Representative role before approval can be granted.

### 5.6 Baseline Audit Trail

The system shall maintain a complete, immutable audit trail of all baseline changes. Each entry in the audit trail shall capture:

- Sequence number
- Date and time of change (UTC)
- User who made the change
- Change type
- Reason for change
- Schedule/cost impact
- Stakeholder comments
- Name of approver

The audit trail shall be viewable within the system and exportable for governance and reporting purposes. For example, a project may show entries such as an initial baseline set at project kickoff, a subsequent entry for a two-day material delivery delay, and a further entry for a five-day scope change following owner re-approval — each with the relevant comments and approvers recorded.

### 5.7 Baseline Deviation Reporting

The system shall provide a baseline comparison view that shows, for each stage or summary milestone, the difference between the currently planned end date and the baseline end date. Deviations shall be presented as a signed number of days (e.g., +2 days delay, -1 day early, or On Baseline).

Visual indicators shall be applied to stages to communicate deviation status at a glance:

- A highlighted indicator for stages running behind the baseline
- A distinct indicator for stages running ahead of the baseline
- No special indicator for stages on baseline

A summary line shall report the count of stages in each deviation state across the project.

### 5.8 Stakeholder Notification Log

The system shall maintain a structured log of all stakeholder communications related to project events, baseline changes, and delays. Each log entry shall record the date, stakeholder name, role, notification type, and any relevant comments. This log shall be auditable and accessible to the project team.

For example, when a baseline is revised following a scope change, the system should automatically generate a notification log entry for the Owner Representative acknowledging the change and capturing their acceptance comment.

### 5.9 Progress & Status Updates

The system shall allow project team members to update the actual start date, actual end date, status, progress percentage, and comments for any stage they are authorized to edit. Updates shall be timestamped and attributed to the editing user. The system shall not allow an actual end date to be recorded without a corresponding actual start date.

---

## 6. Non-Functional Requirements

**Usability:** The Gantt chart interface and all management functions shall be accessible via a standard web browser with no specialist software installation required. The interface shall remain responsive and readable across all configured project sizes.

**Auditability:** All data changes — including stage updates, baseline changes, and change request submissions — shall be logged with the user identity and a UTC timestamp.

**Data Integrity:** Once a baseline is approved, its recorded planned dates shall be protected from modification. Only a new formal baseline change request can alter the reference data.

**Scalability:** The system shall support projects with a variable number of phases and stages, from small projects with fewer than 10 stages to large projects with 50 or more stages, without degradation of performance or usability.

**Traceability:** Every change to schedule or baseline data shall be traceable to an authorized user and a documented, approved reason.

---

## 7. Assumptions & Constraints

- The number of phases and stages in any given project is variable and must be configurable without system-level changes.
- Material deliveries from external suppliers represent a common source of schedule risk and the system must make it easy to log and communicate supplier-related delays.
- Classification society or equivalent third-party approvals may be required at specific stage gates (e.g., hull design sign-off, weld inspection certification); the system should accommodate comment fields and status markers to reflect this.
- All baseline change approvals must follow the defined workflow; verbal or informal approvals are not recognized by the system.
- The planned launch or delivery date for a vessel is treated as a key milestone and should be clearly visible in the project schedule at all times.

---

## 8. Glossary

| Term | Definition |
|------|------------|
| Baseline | An approved, versioned snapshot of the project's planned scope, schedule, and cost, used as the reference for measuring deviation |
| Change Request | A formal submission requesting a modification to the approved baseline, requiring documented justification and approver sign-off |
| Deviation | The difference, in days, between a stage's current planned date and its baseline date |
| Grand Block | A large pre-assembled structural hull module formed from multiple sub-blocks, ready for erection on the slipway or drydock |
| Phase | A named grouping of related project stages representing a major area of work (e.g., Fabrication Preparation, Erection & Assembly) |
| Stage | An individual work activity within a phase, tracked with its own schedule, status, and progress data |
| Erection | The process of joining assembled hull blocks on the slipway or drydock to form the complete hull structure |
| NDT | Non-Destructive Testing — inspection techniques used to evaluate welds and structural components without causing damage |
| WPS | Welding Procedure Specification — a qualified document defining parameters for a specific welding operation |
| MTO | Material Take-Off — a quantified list of materials derived from engineering drawings, used to drive procurement |

---

*This document is intended as a generic requirements baseline for shipyard hull assembly project management systems. All phase structures, stage names, durations, and personnel references used as examples within this document are illustrative only and should be replaced with project-specific values prior to formal use.*