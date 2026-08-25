"use client";

import { EmployeeForm } from "./EmployeeForm";
import { EmployeeList } from "./EmployeeList";
import type { EmployeeMessage } from "./types";
import { useEmployees } from "./useEmployees";

type Props = {
  onMessage: (message: EmployeeMessage | null) => void;
};

export function EmployeesModule({ onMessage }: Props) {
  const employees = useEmployees(onMessage);
  return (
    <div className="grid artist-grid">
      <EmployeeForm
        form={employees.form}
        editingId={employees.editingId}
        loading={employees.loading}
        functionOptions={employees.functionOptions}
        modules={employees.modules}
        artists={employees.artists}
        onFieldChange={employees.updateField}
        onFunctionToggle={employees.toggleFunction}
        onPermissionLevelChange={employees.setPermissionLevel}
        onPermissionArtistModeChange={employees.setPermissionArtistMode}
        onPermissionArtistToggle={employees.togglePermissionArtist}
        onCancel={employees.resetForm}
        onSubmit={employees.submit}
      />
      <EmployeeList
        records={employees.records}
        filteredRecords={employees.filteredRecords}
        moduleCount={employees.modules.length}
        search={employees.search}
        loading={employees.loading}
        onSearchChange={employees.setSearch}
        onRefresh={employees.loadData}
        onEdit={employees.editRecord}
        onResetPassword={employees.resetPassword}
        onDeactivate={employees.deactivateRecord}
      />
    </div>
  );
}
